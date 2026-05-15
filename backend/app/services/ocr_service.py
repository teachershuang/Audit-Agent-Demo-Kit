from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from statistics import mean
import shutil
from typing import Callable

import fitz
from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.data.sample_contract import SAMPLE_CONTRACT_TEXT
from app.logging_utils import app_logger, json_dumps
from app.schemas.contract import ContractPage, DocumentBlock
from app.services.document_service import DocumentPreparation
from app.services.paddle_ocr_service import PaddleOCRLine, PaddleOCRService
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
    def __init__(
        self,
        settings: Settings,
        qwen_service: QwenService,
        paddle_ocr_service: PaddleOCRService,
    ) -> None:
        self.settings = settings
        self.qwen_service = qwen_service
        self.paddle_ocr_service = paddle_ocr_service
        self.max_vl_concurrency = max(1, settings.scanned_vl_concurrency)
        self.scanned_ocr_strategy = (settings.scanned_ocr_strategy or "vl_primary").strip().lower()

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
        cache_entry_dir = self._resolve_cache_dir(preparation=preparation, output_root=output_root)
        cached_document = self._load_cached_document(task_id=task_id, cache_entry_dir=cache_entry_dir, page_dir=page_dir)
        if cached_document is not None:
            self._emit_progress(progress_callback, 20, "ocr_cache_hit", "已命中 OCR 缓存，正在复用页级文本与坐标结果。")
            return cached_document

        if preparation.use_builtin_example:
            self._emit_progress(progress_callback, 16, "document_prepared", "示例合同已准备完成，开始解析。")
            return self._build_example_document(task_id=task_id, image_path=page_dir / "page_001.png")

        if preparation.file_type == "pdf" and preparation.source_path:
            extracted = await self._extract_pdf(
                task_id=task_id,
                file_path=preparation.source_path,
                page_dir=page_dir,
                progress_callback=progress_callback,
            )
            self._persist_cache(cache_entry_dir=cache_entry_dir, extracted=extracted, page_dir=page_dir)
            return extracted

        if preparation.file_type == "image" and preparation.source_path:
            extracted = await self._extract_image(
                task_id=task_id,
                file_path=preparation.source_path,
                page_dir=page_dir,
                progress_callback=progress_callback,
            )
            self._persist_cache(cache_entry_dir=cache_entry_dir, extracted=extracted, page_dir=page_dir)
            return extracted

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
                f"正在渲染 {total_pages} 页合同，并检查是否存在可直接提取的内嵌文本。",
            )
            for page_index in range(total_pages):
                page = doc.load_page(page_index)
                page_number = page_index + 1
                image_path, scale = self._render_pdf_page(page, page_dir / f"page_{page_number:03d}.png")
                width, height = self._image_size(image_path)
                pdf_blocks = self._extract_pdf_text_blocks(page=page, scale=scale)
                text_len = sum(len(block.text.strip()) for block in pdf_blocks)
                if text_len >= 60:
                    pipelines.add("pdf_text")
                    blocks = pdf_blocks
                else:
                    blocks = []
                    ocr_candidates.append(
                        OCRCandidate(
                            page_number=page_number,
                            image_path=image_path,
                            width=width,
                            height=height,
                        )
                    )
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

                page_map[page_number] = ContractPage(
                    page=page_number,
                    title=self._derive_page_title(blocks, fallback=f"Page {page_number}"),
                    width=width,
                    height=height,
                    imageUrl=f"/api/contracts/{task_id}/pages/{page_number}/image",
                    imageLocalPath=str(image_path),
                    blocks=blocks,
                    evidences=[],
                )

        if ocr_candidates:
            scanned_warnings, scanned_pipelines = await self._extract_scanned_candidates(
                page_map=page_map,
                ocr_candidates=ocr_candidates,
                page_dir=page_dir,
                progress_callback=progress_callback,
            )
            warnings.extend(scanned_warnings)
            pipelines.update(scanned_pipelines)

        pages = [page_map[page_number] for page_number in sorted(page_map)]
        full_text = "\n\n".join("\n".join(block.text for block in page.blocks) for page in pages)
        pipeline = "+".join(sorted(pipelines)) if pipelines else "pdf_text"
        self._emit_progress(
            progress_callback,
            58,
            "document_extracted",
            f"文档抽取完成，共生成 {len(pages)} 页可定位文本。",
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
        page = ContractPage(
            page=1,
            title="Page 1",
            width=width,
            height=height,
            imageUrl=f"/api/contracts/{task_id}/pages/1/image",
            imageLocalPath=str(image_path),
            blocks=[],
            evidences=[],
        )

        warnings: list[str] = []
        pipelines: set[str] = set()
        candidate = OCRCandidate(page_number=1, image_path=image_path, width=width, height=height)
        page_warnings, page_pipeline, blocks = await self._build_scanned_page_blocks(candidate, page_dir)
        warnings.extend(page_warnings)
        pipelines.update(page_pipeline)
        page.blocks = blocks
        page.title = self._derive_page_title(blocks, fallback="Page 1")
        self._emit_progress(progress_callback, 58, "document_extracted", "图片合同 OCR 已完成。")
        return ExtractedDocument(
            pages=[page],
            full_text="\n".join(block.text for block in blocks),
            pipeline="+".join(sorted(pipelines)) if pipelines else "scanned_unknown",
            warnings=warnings,
        )

    async def _extract_scanned_candidates(
        self,
        page_map: dict[int, ContractPage],
        ocr_candidates: list[OCRCandidate],
        page_dir: Path,
        progress_callback: ProgressCallback | None,
    ) -> tuple[list[str], set[str]]:
        warnings: list[str] = []
        pipelines: set[str] = set()

        paddle_results: dict[int, list[PaddleOCRLine]] = {}
        should_prefetch_paddle = (
            self.scanned_ocr_strategy == "paddle_primary"
            and self.settings.enable_paddle_ocr
            and self.paddle_ocr_service.is_available
        )
        if should_prefetch_paddle:
            self._emit_progress(
                progress_callback,
                18,
                "paddle_ocr",
                f"正在使用 PaddleOCR 处理 {len(ocr_candidates)} 页扫描页，提取基础文本与坐标。",
            )
            paddle_results = await self.paddle_ocr_service.extract_pages(
                [
                    {"page": candidate.page_number, "image_path": str(candidate.image_path)}
                    for candidate in ocr_candidates
                ]
            )
            if paddle_results:
                pipelines.add("paddle_ocr")

        semaphore = asyncio.Semaphore(self.max_vl_concurrency)
        progress_lock = asyncio.Lock()
        completed_pages = 0
        total_pages = len(ocr_candidates)

        async def process_candidate(candidate: OCRCandidate) -> None:
            nonlocal completed_pages
            page = page_map[candidate.page_number]
            async with semaphore:
                page_warnings, page_pipeline, blocks = await self._build_scanned_page_blocks(
                    candidate=candidate,
                    page_dir=page_dir,
                    paddle_lines=paddle_results.get(candidate.page_number, []),
                )
            page.blocks = blocks
            page.title = self._derive_page_title(blocks, fallback=page.title)
            warnings.extend(page_warnings)
            pipelines.update(page_pipeline)

            async with progress_lock:
                completed_pages += 1
                progress_value = 18 + int((completed_pages / max(total_pages, 1)) * 34)
                message = (
                    f"已完成第 {candidate.page_number} 页扫描识别，当前已处理 {completed_pages}/{total_pages} 页。"
                    if not page_warnings
                    else f"{page_warnings[0]} 当前已处理 {completed_pages}/{total_pages} 页。"
                )
                self._emit_progress(progress_callback, progress_value, "ocr_running", message)

        await asyncio.gather(*(process_candidate(candidate) for candidate in ocr_candidates))
        return warnings, pipelines

    async def _build_scanned_page_blocks(
        self,
        candidate: OCRCandidate,
        page_dir: Path,
        paddle_lines: list[PaddleOCRLine] | None = None,
    ) -> tuple[list[str], set[str], list[DocumentBlock]]:
        warnings: list[str] = []
        pipelines: set[str] = set()
        vl_paragraphs = await self._try_fetch_vl_paragraphs(
            candidate=candidate,
            page_dir=page_dir,
        )
        if vl_paragraphs:
            pipelines.add("qwen_vl_semantic")
        lines = paddle_lines or []

        if self.scanned_ocr_strategy == "vl_primary" and vl_paragraphs:
            if not lines and self.settings.enable_paddle_ocr and self.paddle_ocr_service.is_available:
                extracted = await self.paddle_ocr_service.extract_pages(
                    [{"page": candidate.page_number, "image_path": str(candidate.image_path)}]
                )
                lines = extracted.get(candidate.page_number, [])
                if lines:
                    pipelines.add("paddle_ocr_anchor")

            if lines:
                semantic_blocks = await self._try_align_paragraphs_to_lines(
                    lines=lines,
                    paragraphs=vl_paragraphs,
                    page_number=candidate.page_number,
                )
                if semantic_blocks:
                    pipelines.add("qwen_text_anchor")
                    return warnings, pipelines, semantic_blocks

            vl_blocks = self._build_flow_blocks(
                paragraphs=vl_paragraphs,
                width=candidate.width,
                height=candidate.height,
                page_number=candidate.page_number,
            )
            if vl_blocks:
                pipelines.add("qwen_vl_primary")
                warnings.append(f"Page {candidate.page_number} used VL-primary OCR with approximate boxes")
                return warnings, pipelines, vl_blocks

        if not lines and self.settings.enable_paddle_ocr and self.paddle_ocr_service.is_available:
            extracted = await self.paddle_ocr_service.extract_pages(
                [{"page": candidate.page_number, "image_path": str(candidate.image_path)}]
            )
            lines = extracted.get(candidate.page_number, [])
        lines = lines or []

        if lines:
            pipelines.add("paddle_ocr")
            if vl_paragraphs:
                semantic_blocks = await self._try_align_paragraphs_to_lines(
                    lines=lines,
                    paragraphs=vl_paragraphs,
                    page_number=candidate.page_number,
                )
                if semantic_blocks:
                    pipelines.add("qwen_text_anchor")
                    return warnings, pipelines, semantic_blocks
            return warnings, pipelines, self._group_lines_by_layout(lines, candidate.page_number)

        if vl_paragraphs:
            vl_blocks = self._build_flow_blocks(
                paragraphs=vl_paragraphs,
                width=candidate.width,
                height=candidate.height,
                page_number=candidate.page_number,
            )
            if vl_blocks:
                pipelines.add("qwen_vl_only")
                warnings.append(f"Page {candidate.page_number} used VL-only OCR fallback")
                return warnings, pipelines, vl_blocks

        vl_blocks = await self._try_build_vl_only_blocks(candidate=candidate, page_dir=page_dir)
        if vl_blocks:
            pipelines.add("qwen_vl_only")
            warnings.append(f"Page {candidate.page_number} used VL-only OCR fallback")
            return warnings, pipelines, vl_blocks

        warnings.append(f"Page {candidate.page_number} OCR needs manual review: no text extracted")
        return warnings, pipelines, []

    async def _try_fetch_vl_paragraphs(
        self,
        candidate: OCRCandidate,
        page_dir: Path,
    ) -> list[str]:
        if not self.settings.enable_vl_ocr_enhancement or not self.qwen_service.is_available:
            return []

        try:
            reduced_path = self._prepare_ocr_image(
                source_path=candidate.image_path,
                output_path=page_dir / f"page_{candidate.page_number:03d}_vl.png",
                max_width=960,
            )
            payload = await self.qwen_service.vision_json(
                prompt=(
                    "你正在阅读一页中文扫描合同。"
                    "请只做 OCR 与阅读顺序还原，不要总结，不要解释，不要翻译。"
                    "返回 JSON，对象包含 `full_text` 和 `paragraphs`。"
                    "`paragraphs` 必须是按自然阅读顺序排列的段落数组，只能基于图片中可见文字。"
                ),
                image_path=reduced_path,
                schema={"type": "object"},
                timeout=120,
            )
            return self._normalize_ocr_paragraphs(payload)
        except Exception as exc:
            app_logger.warning(
                json_dumps(
                    {
                        "event": "vl_ocr_enhancement_failed",
                        "page": candidate.page_number,
                        "error": str(exc),
                    }
                )
            )
            return []

    async def _try_align_paragraphs_to_lines(
        self,
        lines: list[PaddleOCRLine],
        paragraphs: list[str],
        page_number: int,
    ) -> list[DocumentBlock]:
        if not paragraphs or not self.qwen_service.is_available:
            return []

        line_payload = [{"id": line.id, "text": line.text} for line in lines[:120]]
        paragraph_payload = paragraphs[:40]
        try:
            payload = await self.qwen_service.chat_json(
                system_prompt=(
                    "你负责把合同语义段落回锚到 OCR 行。"
                    "每个段落只能映射到输入里真实存在的连续 lineIds。"
                    "不要编造 lineIds，不要输出英文。"
                ),
                user_prompt=(
                    f"OCR lines: {line_payload}\n"
                    f"Semantic paragraphs: {paragraph_payload}\n"
                    "请返回 JSON 对象，顶层字段为 `groups`。"
                    "每个 group 包含 `paragraph` 和 `lineIds`。"
                ),
                schema={"type": "object"},
            )
        except Exception as exc:
            app_logger.warning(json_dumps({"event": "text_anchor_alignment_failed", "error": str(exc)}))
            return []

        groups = payload.get("groups")
        if not isinstance(groups, list):
            return []

        line_index = {line.id: idx for idx, line in enumerate(lines)}
        blocks: list[DocumentBlock] = []
        seen_ids: set[str] = set()
        for index, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                continue
            line_ids = [str(item) for item in group.get("lineIds", []) if str(item).strip()]
            if not line_ids:
                continue
            if any(line_id not in line_index for line_id in line_ids):
                continue
            ordered_indices = [line_index[line_id] for line_id in line_ids]
            if ordered_indices != list(range(min(ordered_indices), max(ordered_indices) + 1)):
                continue
            selected_lines = [lines[idx] for idx in ordered_indices]
            block_text = " ".join(line.text for line in selected_lines).strip()
            blocks.append(
                self._merge_lines_into_block(
                    selected_lines,
                    f"hybrid_{page_number:03d}_{index:03d}",
                    block_text,
                )
            )
            seen_ids.update(line_ids)

        if not blocks:
            return []

        if self._semantic_alignment_looks_unstable(lines, blocks):
            return []

        for line in lines:
            if line.id in seen_ids:
                continue
            blocks.append(self._merge_lines_into_block([line], f"hybrid_tail_{line.id}", line.text))

        blocks.sort(key=lambda block: (block.y, block.x))
        return blocks

    async def _try_build_vl_only_blocks(
        self,
        candidate: OCRCandidate,
        page_dir: Path,
    ) -> list[DocumentBlock]:
        if not self.qwen_service.is_available:
            return []
        try:
            reduced_path = self._prepare_ocr_image(
                source_path=candidate.image_path,
                output_path=page_dir / f"page_{candidate.page_number:03d}_vl_fallback.png",
                max_width=960,
            )
            payload = await self.qwen_service.vision_json(
                prompt=(
                    "You are an OCR assistant for Chinese contracts. Read the page in natural reading order and "
                    "return a JSON object with two fields: `full_text` and `paragraphs`. "
                    "`paragraphs` must be an ordered array of paragraph strings. "
                    "Do not invent content that is not visible in the image."
                ),
                image_path=reduced_path,
                schema={"type": "object"},
                timeout=120,
            )
            paragraphs = self._normalize_ocr_paragraphs(payload)
            if not paragraphs:
                return []
            return self._build_flow_blocks(
                paragraphs=paragraphs,
                width=candidate.width,
                height=candidate.height,
                page_number=candidate.page_number,
            )
        except Exception as exc:
            app_logger.warning(
                json_dumps(
                    {
                        "event": "vl_only_fallback_failed",
                        "page": candidate.page_number,
                        "error": str(exc),
                    }
                )
            )
            return []

    @staticmethod
    def _should_use_vl_enhancement(lines: list[PaddleOCRLine]) -> bool:
        if not lines:
            return False
        avg_score = mean(line.score for line in lines)
        short_ratio = sum(1 for line in lines if len(line.text.strip()) <= 2) / len(lines)
        fragmented_ratio = sum(1 for line in lines if len(line.text.strip()) <= 6) / len(lines)
        severe_quality_drop = avg_score < 0.82
        low_confidence_fragmentation = avg_score < 0.90 and short_ratio > 0.55
        dense_unstable_layout = avg_score < 0.93 and len(lines) >= 45 and fragmented_ratio > 0.72
        return severe_quality_drop or low_confidence_fragmentation or dense_unstable_layout

    @staticmethod
    def _group_lines_by_layout(lines: list[PaddleOCRLine], page_number: int) -> list[DocumentBlock]:
        if not lines:
            return []
        blocks: list[DocumentBlock] = []
        cluster: list[PaddleOCRLine] = [lines[0]]
        block_index = 1
        for current in lines[1:]:
            prev = cluster[-1]
            prev_bottom = prev.y + prev.height
            gap = current.y - prev_bottom
            similar_indent = abs(current.x - prev.x) < 48
            if gap <= max(prev.height, current.height) * 1.2 and similar_indent:
                cluster.append(current)
                continue
            blocks.append(
                OCRService._merge_lines_into_block(cluster, f"paddle_{page_number:03d}_{block_index:03d}")
            )
            block_index += 1
            cluster = [current]
        if cluster:
            blocks.append(
                OCRService._merge_lines_into_block(cluster, f"paddle_{page_number:03d}_{block_index:03d}")
            )
        return blocks

    @staticmethod
    def _merge_lines_into_block(
        lines: list[PaddleOCRLine],
        block_id: str,
        override_text: str | None = None,
    ) -> DocumentBlock:
        min_x = min(line.x for line in lines)
        min_y = min(line.y for line in lines)
        max_x = max(line.x + line.width for line in lines)
        max_y = max(line.y + line.height for line in lines)
        text = override_text or " ".join(line.text for line in lines)
        return DocumentBlock(
            id=block_id,
            text=text.strip(),
            x=min_x,
            y=min_y,
            width=max(1, max_x - min_x),
            height=max(1, max_y - min_y),
            emphasis=OCRService._looks_like_heading(text),
        )

    @staticmethod
    def _semantic_alignment_looks_unstable(
        lines: list[PaddleOCRLine],
        blocks: list[DocumentBlock],
    ) -> bool:
        if not blocks:
            return True
        average_line_height = mean(max(1, line.height) for line in lines) if lines else 1
        oversized_blocks = sum(1 for block in blocks if block.height > average_line_height * 4.5)
        tiny_blocks = sum(1 for block in blocks if len(block.text.strip()) <= 1)
        return oversized_blocks > max(1, len(blocks) // 4) or tiny_blocks > max(2, len(blocks) // 3)

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
            imageLocalPath=str(image_path),
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
    def _build_flow_blocks(paragraphs: list[str], width: int, height: int, page_number: int) -> list[DocumentBlock]:
        usable_paragraphs = [item for item in paragraphs if item]
        if not usable_paragraphs:
            return []

        horizontal_padding = max(36, int(width * 0.08))
        top_padding = max(36, int(height * 0.05))
        usable_width = max(320, width - horizontal_padding * 2)
        line_height = max(28, int(height * 0.024))
        gap = max(12, int(line_height * 0.45))

        current_y = top_padding
        blocks: list[DocumentBlock] = []
        for index, text in enumerate(usable_paragraphs, start=1):
            unit_count = max(1, len(text) // 28 + 1)
            block_height = max(line_height, int(line_height * unit_count))
            blocks.append(
                DocumentBlock(
                    id=f"vl_{page_number:03d}_{index:03d}",
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
        if len(compact) <= 24 and compact.startswith(("一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、")):
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

    def _resolve_cache_dir(self, preparation: DocumentPreparation, output_root: Path) -> Path | None:
        if not self.settings.ocr_cache_enabled or preparation.use_builtin_example or not preparation.source_path:
            return None
        try:
            digest = self._file_digest(preparation.source_path)
        except Exception:
            return None
        cache_dir = output_root / "_cache" / self.settings.ocr_cache_namespace / digest
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _load_cached_document(
        self,
        task_id: str,
        cache_entry_dir: Path | None,
        page_dir: Path,
    ) -> ExtractedDocument | None:
        if cache_entry_dir is None:
            return None
        metadata_path = cache_entry_dir / "extracted_document.json"
        cached_pages_dir = cache_entry_dir / "pages"
        if not metadata_path.exists() or not cached_pages_dir.exists():
            return None
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            for cached_image in sorted(cached_pages_dir.glob("page_*.png")):
                shutil.copy2(cached_image, page_dir / cached_image.name)
            pages: list[ContractPage] = []
            for raw_page in payload.get("pages", []):
                page = ContractPage.model_validate(raw_page)
                page.blocks = self._normalize_cached_block_ids(page)
                page.imageUrl = f"/api/contracts/{task_id}/pages/{page.page}/image"
                page.imageLocalPath = str(page_dir / f"page_{page.page:03d}.png")
                pages.append(page)
            return ExtractedDocument(
                pages=pages,
                full_text=str(payload.get("full_text") or ""),
                pipeline=str(payload.get("pipeline") or "ocr_cache"),
                warnings=[str(item) for item in payload.get("warnings", [])],
            )
        except Exception as exc:
            app_logger.warning(
                json_dumps(
                    {
                        "event": "ocr_cache_load_failed",
                        "cacheDir": str(cache_entry_dir),
                        "error": str(exc),
                    }
                )
            )
            return None

    @staticmethod
    def _normalize_cached_block_ids(page: ContractPage) -> list[DocumentBlock]:
        normalized: list[DocumentBlock] = []
        for index, block in enumerate(page.blocks, start=1):
            block_id = block.id
            if block_id.startswith(("paddle_", "hybrid_", "vl_")) and f"_{page.page:03d}_" not in block_id:
                if block_id.startswith("paddle_"):
                    block_id = f"paddle_{page.page:03d}_{index:03d}"
                elif block_id.startswith("hybrid_"):
                    block_id = f"hybrid_{page.page:03d}_{index:03d}"
                elif block_id.startswith("vl_"):
                    block_id = f"vl_{page.page:03d}_{index:03d}"
            normalized.append(
                DocumentBlock(
                    id=block_id,
                    text=block.text,
                    x=block.x,
                    y=block.y,
                    width=block.width,
                    height=block.height,
                    emphasis=block.emphasis,
                )
            )
        return normalized

    def _persist_cache(
        self,
        cache_entry_dir: Path | None,
        extracted: ExtractedDocument,
        page_dir: Path,
    ) -> None:
        if cache_entry_dir is None:
            return
        try:
            cached_pages_dir = cache_entry_dir / "pages"
            cached_pages_dir.mkdir(parents=True, exist_ok=True)
            for image_path in sorted(page_dir.glob("page_*.png")):
                target_path = cached_pages_dir / image_path.name
                if not target_path.exists():
                    shutil.copy2(image_path, target_path)
            payload = {
                "pages": [page.model_dump() for page in extracted.pages],
                "full_text": extracted.full_text,
                "pipeline": extracted.pipeline,
                "warnings": extracted.warnings,
            }
            (cache_entry_dir / "extracted_document.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            app_logger.warning(
                json_dumps(
                    {
                        "event": "ocr_cache_persist_failed",
                        "cacheDir": str(cache_entry_dir),
                        "error": str(exc),
                    }
                )
            )

    @staticmethod
    def _file_digest(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
