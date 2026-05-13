from __future__ import annotations

from app.mock.sample_result import build_mock_pages
from app.tools.base_tool import BaseTool


class MockOcrTool(BaseTool):
    name = "mock_ocr_tool"

    def run(self):
        return build_mock_pages()
