from __future__ import annotations

from pathlib import Path

from docx import Document

from app.parser.text_cleaner import clean_text


class DOCXParser:
    def parse(self, file_path: Path) -> dict:
        document = Document(file_path)
        paragraphs = [clean_text(paragraph.text) for paragraph in document.paragraphs if paragraph.text.strip()]
        text = "\n".join(item for item in paragraphs if item)
        return {
            "text": clean_text(text),
            "pages": [{"page": 1, "text": clean_text(text)}],
            "toc": [],
            "page_count": 1,
        }
