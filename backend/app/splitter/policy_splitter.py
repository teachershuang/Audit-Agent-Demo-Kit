from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.parser.text_cleaner import clean_text


class PolicySplitter:
    chapter_pattern = re.compile(r"(第[一二三四五六七八九十百千]+章[^\n]*)")
    article_pattern = re.compile(r"(第[一二三四五六七八九十百千]+条[^\n]*)")

    def split(self, text: str, document_id: str, effective_ts: int, abolish_ts: int) -> list[dict[str, Any]]:
        normalized = clean_text(text)
        chapters = self.chapter_pattern.split(normalized)
        current_chapter = "总则"
        clauses: list[dict[str, Any]] = []

        for chapter_chunk in chapters:
            chunk = chapter_chunk.strip()
            if not chunk:
                continue
            if self.chapter_pattern.fullmatch(chunk):
                current_chapter = chunk
                continue
            parts = self.article_pattern.split(chunk)
            current_article = None
            for part in parts:
                item = part.strip()
                if not item:
                    continue
                if self.article_pattern.fullmatch(item):
                    current_article = item
                    continue
                title = current_article or current_chapter
                clause_no = current_article.split("条", 1)[0] if current_article else current_chapter
                content = clean_text(item)
                if not content:
                    continue
                clauses.append(
                    {
                        "id": f"clause_{uuid4().hex[:16]}",
                        "document_id": document_id,
                        "doc_type": "policy",
                        "template_id": None,
                        "template_name": None,
                        "category_lv1": current_chapter,
                        "category_lv2": None,
                        "clause_no": clause_no,
                        "title": title,
                        "clause_type": "policy_article",
                        "content": content,
                        "page_start": 1,
                        "page_end": 1,
                        "status": "effective",
                        "effective_ts": effective_ts,
                        "abolish_ts": abolish_ts,
                        "risk_tags": [],
                    }
                )
        return clauses
