from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

from app.data.sample_contract import SAMPLE_CONTRACT_TEXT
from app.schemas.contract import ContractPage, DocumentBlock
from app.services.document_service import DocumentPreparation
from app.services.qwen_service import QwenService


@dataclass
class ExtractedDocument:
    pages: list[ContractPage]
    full_text: str
    pipeline: str


class OCRService:
    def __init__(self, qwen_service: QwenService) -> None:
        self.qwen_service = qwen_service

    async def extract_document(
        self,
        task_id: str,
        preparation: DocumentPreparation,
        output_root: Path,
    ) -> ExtractedDocument:
        task_dir = output_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        page_dir = task_dir / "pages"
        page_dir.mkdir(parents=True, exist_ok=True)

        if preparation.use_builtin_example:
            return self._build_example_document(task_id=task_id, image_path=page_dir / "page_001.png")

        if preparation.file_type == "pdf" and preparation.source_path:
            return await self._extract_pdf(task_id=task_id, file_path=preparation.source_path, page_dir=page_dir)

        if preparation.file_type == "image" and preparation.source_path:
            return await self._extract_image(task_id=task_id, file_path=preparation.source_path, page_dir=page_dir)

        raise RuntimeError("Unsupported document type.")

    async def _extract_pdf(self, task_id: str, file_path: Path, page_dir: Path) -> ExtractedDocument:
        pages: list[ContractPage] = []
        full_text_parts: list[str] = []
        pipelines: set[str] = set()

        with fitz.open(file_path) as doc:
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                image_path, scale = self._render_pdf_page(page, page_dir / f"page_{page_index + 1:03d}.png")
                width, height = self._image_size(image_path)

                blocks = self._extract_pdf_text_blocks(page=page, scale=scale)
                text_len = sum(len(block.text.strip()) for block in blocks)
                if text_len < 60:
                    blocks = await self._ocr_image_blocks(image_path=image_path, width=width, height=height)
                    pipelines.add("qwen_vl_ocr")
                else:
                    pipelines.add("pdf_text")

                contract_page = ContractPage(
                    page=page_index + 1,
                    title=self._derive_page_title(blocks, fallback=f"第 {page_index + 1} 页"),
                    width=width,
                    height=height,
                    imageUrl=f"/api/contracts/{task_id}/pages/{page_index + 1}/image",
                    blocks=blocks,
                    evidences=[],
                )
                pages.append(contract_page)
                full_text_parts.append("\n".join(block.text for block in blocks))

        pipeline = "+".join(sorted(pipelines)) if pipelines else "pdf_text"
        return ExtractedDocument(pages=pages, full_text="\n\n".join(full_text_parts), pipeline=pipeline)

    async def _extract_image(self, task_id: str, file_path: Path, page_dir: Path) -> ExtractedDocument:
        image = Image.open(file_path).convert("RGB")
        image_path = page_dir / "page_001.png"
        image.save(image_path)
        width, height = image.size
        blocks = await self._ocr_image_blocks(image_path=image_path, width=width, height=height)
        page = ContractPage(
            page=1,
            title=self._derive_page_title(blocks, fallback="第 1 页"),
            width=width,
            height=height,
            imageUrl=f"/api/contracts/{task_id}/pages/1/image",
            blocks=blocks,
            evidences=[],
        )
        full_text = "\n".join(block.text for block in blocks)
        return ExtractedDocument(pages=[page], full_text=full_text, pipeline="qwen_vl_ocr")

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
            title="信息化系统实施服务合同",
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

    async def _ocr_image_blocks(self, image_path: Path, width: int, height: int) -> list[DocumentBlock]:
        payload = await self.qwen_service.vision_json(
            prompt=(
                "你是合同 OCR 抽取助手。请读取图片中的文本并按阅读顺序输出文本块。"
                "返回 JSON 对象，包含 blocks 数组。每个 block 需要包含 text 和 bbox。"
                "bbox 使用 0-1000 的归一化坐标，格式为 [x, y, width, height]。"
                "不要编造图片中不存在的内容。"
            ),
            image_path=image_path,
            schema={"type": "object"},
        )

        blocks: list[DocumentBlock] = []
        raw_blocks = self._normalize_ocr_payload(payload)
        for index, item in enumerate(raw_blocks, start=1):
            text = str(item["text"]).strip()
            if not text:
                continue
            x, y, w, h = [float(value) for value in item["bbox"]]
            blocks.append(
                DocumentBlock(
                    id=f"ocr_{index:03d}",
                    text=text,
                    x=int(max(0, min(1000, x)) / 1000 * width),
                    y=int(max(0, min(1000, y)) / 1000 * height),
                    width=max(40, int(max(0, min(1000, w)) / 1000 * width)),
                    height=max(20, int(max(0, min(1000, h)) / 1000 * height)),
                    emphasis=self._looks_like_heading(text),
                )
            )

        blocks.sort(key=lambda block: (block.y, block.x))
        return blocks

    @staticmethod
    def _normalize_ocr_payload(payload: dict) -> list[dict]:
        if isinstance(payload.get("blocks"), list):
            return [item for item in payload["blocks"] if isinstance(item, dict)]
        if isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        if "text" in payload and "bbox" in payload:
            return [payload]
        return []

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
