from __future__ import annotations

from app.mock.sample_result import build_mock_pages
from app.schemas.contract import ContractPage
from app.tools.mock_ocr_tool import MockOcrTool


class OCRService:
    def __init__(self, mock_ocr_tool: MockOcrTool) -> None:
        self.mock_ocr_tool = mock_ocr_tool

    def extract_pages(self) -> list[ContractPage]:
        return self.mock_ocr_tool.run() or build_mock_pages()
