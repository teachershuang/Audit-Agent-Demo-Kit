from __future__ import annotations

from pathlib import Path

import fitz

from app.parser.text_cleaner import clean_text


class PDFParser:
    def parse(self, file_path: Path) -> dict:
        document = fitz.open(file_path)
        pages: list[dict] = []
        for page_number in range(document.page_count):
            page = document.load_page(page_number)
            pages.append(
                {
                    "page": page_number + 1,
                    "text": clean_text(page.get_text("text")),
                }
            )
        return {
            "text": clean_text("\n\n".join(item["text"] for item in pages)),
            "pages": pages,
            "toc": document.get_toc(simple=True),
            "page_count": document.page_count,
        }
