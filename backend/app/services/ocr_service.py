from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
from pathlib import Path
from time import perf_counter
from typing import Callable

import fitz
from PIL import Image, ImageDraw, ImageFont

from app.data.sample_contract import SAMPLE_CONTRACT_TEXT
from app.logging_utils import app_logger, json_dumps
from app.schemas.contract import ContractPage, DocumentBlock
from app.services.document_service import DocumentPreparation
from app.services.qwen_service import QwenService

ProgressCallback = Callable[[int, str, str], None]


@dataclass
class ExtractedDocument:
    pages: list[ContractPage]
    full_text: str
    pipeline: str
    warnings: list[str]


@dataclass
class OCRCandidate:
    page_number: int
    image_path: Path
    width: int
    height: int


class OCRService:
    def __init__(self, qwen_service: QwenService, max_ocr_concurrency: int = 2) -> None:
        self.qwen_service = qwen_service
        self.max_ocr_concurrency = max_ocr_concurrency

    async def extract_document(
        self,
        task_id: str,
        preparation: DocumentPreparation,
        output_root: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> ExtractedDocument:
        task_dir = output_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        page_dir = task_dir / "pages"
        page_dir.mkdir(parents=True, exist_ok=True)

        if preparation.use_builtin_example:
            self._emit_progress(progress_callback, 16, "document_prepared", "Example contract is ready.")
            return self._build_example_document(task_id=task_id, image_path=page_dir / "page_001.png")

        if preparation.file_type == "pdf" and preparation.source_path:
            return await self._extract_pdf(
                task_id=task_id,
                file_path=preparation.source_path,
                page_dir=page_dir,
                progress_callback=progress_callback,
            )

        if preparation.file_type == "image" and preparation.source_path:
            return await self._extract_image(
                task_id=task_id,
                file_path=preparation.source_path,
                page_dir=page_dir,
                progress_callback=progress_callback,
            )

        raise RuntimeError("Unsupported document type.")

    async def _extract_pdf(
        self,
        task_id: str,
        file_path: Path,
        page_dir: Path,
        progress_callback: ProgressCallback | None,
    ) -> ExtractedDocument:
        page_map: dict[int, ContractPage] = {}
        ocr_candidates: list[OCRCandidate] = []
        pipelines: set[str] = set()
        warnings: list[str] = []

        with fitz.open(file_path) as doc:
            total_pages = doc.page_count
            self._emit_progress(
                progress_callback,
                12,
                "document_rendering",
                f"Rendering {total_pages} pages and checking embedded text.",
            )
            for page_index in range(total_pages):
                page = doc.load_page(page_index)
                page_number = page_index + 1
                image_path, scale = self._render_pdf_page(page, page_dir / f"page_{page_number:03d}.png")
                width, height = self._image_size(image_path)
                blocks = self._extract_pdf_text_blocks(page=page, scale=scale)
                text_len = sum(len(block.text.strip()) for block in blocks)
                if text_len >= 60:
                    pipelines.add("pdf_text")
                else:
                    app_logger.info(
                        json_dumps(
                            {
                                "event": "ocr_page_fallback_started",
                                "source": "pdf_scan_page",
                                "page": page_number,
                                "imagePath": str(image_path),
                                "width": width,
                                "height": height,
                                "reason": "pdf_text_too_short",
                                "textLength": text_len,
                            }
                        )
                    )
                    ocr_candidates.append(
                        OCRCandidate(
                            page_number=page_number,
                            image_path=image_path,
                            width=width,
                            height=height,
                        )
                    )

                page_map[page_number] = ContractPage(
                    page=page_number,
                    title=self._derive_page_title(blocks, fallback=f"Page {page_number}"),
                    width=width,
                    height=height,
                    imageUrl=f"/api/contracts/{task_id}/pages/{page_number}/image",
                    blocks=blocks,
                    evidences=[],
                )

        if ocr_candidates:
            pipelines.add("qwen_vl_text_ocr")
            self._emit_progress(
                progress_callback,
                18,
                "ocr_started",
                f"Starting OCR for {len(ocr_candidates)} scanned pages with concurrency {self.max_ocr_concurrency}.",
            )
            warnings.extend(
                await self._resolve_ocr_candidates(page_map, ocr_candidates, page_dir, progress_callback)
            )

        pages = [page_map[page_number] for page_number in sorted(page_map)]
        full_text = "\n\n".join("\n".join(block.text for block in page.blocks) for page in pages)
        pipeline = "+".join(sorted(pipelines)) if pipelines else "pdf_text"
        self._emit_progress(
            progress_callback,
            58,
            "document_extracted",
            f"Document text extraction finished for {len(pages)} pages.",
        )
        return ExtractedDocument(pages=pages, full_text=full_text, pipeline=pipeline, warnings=warnings)

    async def _extract_image(
        self,
        task_id: str,
        file_path: Path,
        page_dir: Path,
        progress_callback: ProgressCallback | None,
    ) -> ExtractedDocument:
        image = Image.open(file_path).convert("RGB")
        image_path = page_dir / "page_001.png"
        image.save(image_path)
        width, height = image.size
        self._emit_progress(progress_callback, 14, "ocr_started", "Starting OCR for uploaded image.")
        blocks = await self._ocr_image_with_retries(
            page_number=1,
            image_path=image_path,
            width=width,
            height=height,
            ocr_output_path=page_dir / "page_001_ocr.png",
        )
        page = ContractPage(
            page=1,
            title=self._derive_page_title(blocks, fallback="Page 1"),
            width=width,
            height=height,
            imageUrl=f"/api/contracts/{task_id}/pages/1/image",
            blocks=blocks,
            evidences=[],
        )
        self._emit_progress(progress_callback, 58, "document_extracted", "Image OCR finished.")
        return ExtractedDocument(
            pages=[page],
            full_text="\n".join(block.text for block in blocks),
            pipeline="qwen_vl_text_ocr",
            warnings=[],
        )

    async def _resolve_ocr_candidates(
        self,
        page_map: dict[int, ContractPage],
        ocr_candidates: list[OCRCandidate],
        page_dir: Path,
        progress_callback: ProgressCallback | None,
    ) -> list[str]:
        semaphore = asyncio.Semaphore(self.max_ocr_concurrency)
        progress_lock = asyncio.Lock()
        completed_pages = 0
        total_pages = len(ocr_candidates)
        warnings: list[str] = []

        async def process_candidate(candidate: OCRCandidate) -> None:
            nonlocal completed_pages
            async with semaphore:
                started = perf_counter()
                page = page_map[candidate.page_number]
                warning_message: str | None = None
                try:
                    blocks = await self._ocr_image_with_retries(
                        page_number=candidate.page_number,
                        image_path=candidate.image_path,
                        width=candidate.width,
                        height=candidate.height,
                        ocr_output_path=page_dir / f"page_{candidate.page_number:03d}_ocr.png",
                    )
                    page.blocks = blocks
                    page.title = self._derive_page_title(blocks, fallback=page.title)
                except Exception as exc:
                    page.blocks = []
                    warning_message = f"Page {candidate.page_number} OCR needs manual review: {exc}"
                    warnings.append(warning_message)
                duration_ms = int((perf_counter() - started) * 1000)

            async with progress_lock:
                completed_pages += 1
                progress_value = 18 + int((completed_pages / max(total_pages, 1)) * 34)
                self._emit_progress(
                    progress_callback,
                    progress_value,
                    "ocr_running",
                    (
                        f"OCR completed for page {candidate.page_number}/{page_map.__len__()} in {round(duration_ms / 1000, 1)}s. "
                        f"Finished {completed_pages}/{total_pages} scanned pages."
                        if warning_message is None
                        else f"{warning_message}. Finished {completed_pages}/{total_pages} scanned pages."
                    ),
                )

        await asyncio.gather(*(process_candidate(candidate) for candidate in ocr_candidates))
        return warnings

    async def _ocr_image_with_retries(
        self,
        page_number: int,
        image_path: Path,
        width: int,
        height: int,
        ocr_output_path: Path,
    ) -> list[DocumentBlock]:
        attempts = [(640, 180), (480, 240)]
        last_error: Exception | None = None
        for attempt_index, (max_width, timeout_seconds) in enumerate(attempts, start=1):
            try:
                prepared_image = self._prepare_ocr_image(
                    source_path=image_path,
                    output_path=ocr_output_path,
                    max_width=max_width,
                )
                blocks = await self._ocr_image_blocks(
                    image_path=prepared_image,
                    width=width,
                    height=height,
                    timeout_seconds=timeout_seconds,
                )
                app_logger.info(
                    json_dumps(
                        {
                            "event": "ocr_page_attempt_succeeded",
                            "page": page_number,
                            "attempt": attempt_index,
                            "ocrWidthCap": max_width,
                            "timeoutSeconds": timeout_seconds,
                            "blockCount": len(blocks),
                        }
                    )
                )
                return blocks
            except Exception as exc:
                last_error = exc
                app_logger.warning(
                    json_dumps(
                        {
                            "event": "ocr_page_attempt_failed",
                            "page": page_number,
                            "attempt": attempt_index,
                            "ocrWidthCap": max_width,
                            "timeoutSeconds": timeout_seconds,
                            "error": str(exc),
                        }
                    )
                )

        raise RuntimeError(f"OCR failed on page {page_number}: {last_error}") from last_error

    def _build_example_document(self, task_id: str, image_path: Path) -> ExtractedDocument:
        width, height = 1440, 1960
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        title_font = self._load_font(34)
        body_font = self._load_font(24)
        y = 88
        lines = [line.strip() for line in SAMPLE_CONTRACT_TEXT.splitlines() if line.strip()]
        blocks: list[DocumentBlock] = []
        for index, line in enumerate(lines):
            font = title_font if index == 0 else body_font
            draw.text((96, y), line, fill="black", font=font)
            blocks.append(
                DocumentBlock(
                    id=f"example_{index + 1:03d}",
                    text=line,
                    x=96,
                    y=y,
                    width=min(width - 192, max(300, int(len(line) * 24))),
                    height=40 if index == 0 else 28,
                    emphasis=index == 0 or self._looks_like_heading(line),
                )
            )
            y += 62 if len(line) < 26 else 74
        image.save(image_path)
        page = ContractPage(
            page=1,
            title="Example Contract",
            width=width,
            height=height,
            imageUrl=f"/api/contracts/{task_id}/pages/1/image",
            blocks=blocks,
            evidences=[],
        )
        return ExtractedDocument(
            pages=[page],
            full_text="\n".join(lines),
            pipeline="example_rendered_text",
            warnings=[],
        )

    @staticmethod
    def _render_pdf_page(page: fitz.Page, output_path: Path) -> tuple[Path, float]:
        matrix = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(output_path)
        scale = pix.width / page.rect.width
        return output_path, scale

    @staticmethod
    def _extract_pdf_text_blocks(page: fitz.Page, scale: float) -> list[DocumentBlock]:
        page_dict = page.get_text("dict")
        blocks: list[DocumentBlock] = []
        block_index = 1
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue

            lines: list[str] = []
            for line in block.get("lines", []):
                span_text = "".join(span.get("text", "") for span in line.get("spans", []))
                span_text = span_text.strip()
                if span_text:
                    lines.append(span_text)

            text = " ".join(lines).strip()
            if not text:
                continue

            x0, y0, x1, y1 = block.get("bbox", [0, 0, 0, 0])
            blocks.append(
                DocumentBlock(
                    id=f"pdf_{page.number + 1:03d}_{block_index:03d}",
                    text=text,
                    x=int(x0 * scale),
                    y=int(y0 * scale),
                    width=max(40, int((x1 - x0) * scale)),
                    height=max(20, int((y1 - y0) * scale)),
                    emphasis=OCRService._looks_like_heading(text),
                )
            )
            block_index += 1
        return blocks

    async def _ocr_image_blocks(
        self,
        image_path: Path,
        width: int,
        height: int,
        timeout_seconds: int,
    ) -> list[DocumentBlock]:
        payload = await self.qwen_service.vision_json(
            prompt=(
                "You are an OCR assistant for Chinese contracts. Read the page in natural reading order and "
                "return a JSON object with two fields: `full_text` and `paragraphs`. "
                "`paragraphs` must be an ordered array of paragraph strings. "
                "Do not invent content that is not visible in the image."
            ),
            image_path=image_path,
            schema={"type": "object"},
            timeout=timeout_seconds,
        )

        paragraphs = self._normalize_ocr_paragraphs(payload)
        if not paragraphs:
            raise RuntimeError("Scanned page OCR returned no readable text.")

        blocks = self._build_flow_blocks(paragraphs=paragraphs, width=width, height=height)
        app_logger.info(
            json_dumps(
                {
                    "event": "ocr_page_fallback_completed",
                    "source": "vision_text_ocr",
                    "imagePath": str(image_path),
                    "width": width,
                    "height": height,
                    "blockCount": len(blocks),
                    "charCount": sum(len(block.text) for block in blocks),
                }
            )
        )
        return blocks

    @staticmethod
    def _normalize_ocr_paragraphs(payload: dict) -> list[str]:
        paragraphs = payload.get("paragraphs")
        if isinstance(paragraphs, list):
            cleaned = [OCRService._clean_ocr_text(item) for item in paragraphs if str(item or "").strip()]
            return [item for item in cleaned if item]

        full_text = OCRService._clean_ocr_text(payload.get("full_text") or payload.get("text") or "")
        if not full_text:
            return []
        split_candidates = [item.strip() for item in full_text.splitlines() if item.strip()]
        if split_candidates:
            return split_candidates
        return [full_text]

    @staticmethod
    def _build_flow_blocks(paragraphs: list[str], width: int, height: int) -> list[DocumentBlock]:
        usable_paragraphs = [item for item in paragraphs if item]
        if not usable_paragraphs:
            return []

        horizontal_padding = max(36, int(width * 0.08))
        top_padding = max(36, int(height * 0.05))
        usable_width = max(320, width - horizontal_padding * 2)
        usable_height = max(300, height - top_padding * 2)
        line_height = max(28, int(height * 0.024))
        gap = max(12, int(line_height * 0.45))

        units = [max(1, math.ceil(len(text) / 28)) for text in usable_paragraphs]
        total_units = sum(units) + max(0, len(usable_paragraphs) - 1)
        scale = min(1.45, usable_height / max(line_height * total_units, 1))

        current_y = top_padding
        blocks: list[DocumentBlock] = []
        for index, text in enumerate(usable_paragraphs, start=1):
            unit_count = units[index - 1]
            block_height = max(line_height, int(line_height * unit_count * scale))
            blocks.append(
                DocumentBlock(
                    id=f"ocr_{index:03d}",
                    text=text,
                    x=horizontal_padding,
                    y=min(current_y, max(top_padding, height - block_height - top_padding)),
                    width=usable_width,
                    height=block_height,
                    emphasis=OCRService._looks_like_heading(text),
                )
            )
            current_y += block_height + gap

        return blocks

    @staticmethod
    def _clean_ocr_text(value: object) -> str:
        text = str(value or "").replace("\u3000", " ").replace("\r", "\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines).strip()

    @staticmethod
    def _prepare_ocr_image(source_path: Path, output_path: Path, max_width: int) -> Path:
        with Image.open(source_path) as image:
            working = image.convert("RGB")
            if working.width > max_width:
                resized_height = max(1, int(working.height * (max_width / working.width)))
                working = working.resize((max_width, resized_height), Image.Resampling.LANCZOS)
                working.save(output_path)
                return output_path
        return source_path

    @staticmethod
    def _image_size(image_path: Path) -> tuple[int, int]:
        with Image.open(image_path) as image:
            return image.size

    @staticmethod
    def _derive_page_title(blocks: list[DocumentBlock], fallback: str) -> str:
        for block in blocks:
            if block.emphasis and len(block.text) <= 32:
                return block.text
        if blocks:
            return blocks[0].text[:32]
        return fallback

    @staticmethod
    def _looks_like_heading(text: str) -> bool:
        compact = text.strip()
        if len(compact) <= 24 and compact.startswith(
            ("一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、")
        ):
            return True
        if len(compact) <= 26 and any(token in compact for token in ("合同", "条款", "标准", "金额", "付款")):
            return True
        return False

    @staticmethod
    def _emit_progress(
        progress_callback: ProgressCallback | None,
        progress_percent: int,
        current_stage: str,
        stage_detail: str,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(progress_percent, current_stage, stage_detail)

    @staticmethod
    def _load_font(size: int) -> ImageFont.ImageFont:
        for font_name in (
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ):
            try:
                return ImageFont.truetype(font_name, size=size)
            except Exception:
                continue
        return ImageFont.load_default()
