from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.parser.text_cleaner import clean_text


class ClauseSplitter:
    heading_patterns = [
        re.compile(r"(?=第[一二三四五六七八九十百千]+条)"),
        re.compile(r"(?=\n[一二三四五六七八九十]+、)"),
        re.compile(r"(?=\n\d+\.\d+(?:\.\d+)?[^\d])"),
    ]

    def split_template_text(
        self,
        *,
        text: str,
        document_id: str,
        template_id: str,
        template_name: str,
        category_lv1: str | None,
        category_lv2: str | None,
        effective_ts: int,
        abolish_ts: int,
        page_start: int,
        page_end: int,
    ) -> list[dict[str, Any]]:
        normalized = clean_text(text)
        parts = [normalized]
        for pattern in self.heading_patterns:
            next_parts: list[str] = []
            for item in parts:
                split_items = [segment.strip() for segment in pattern.split(item) if segment.strip()]
                if split_items:
                    next_parts.extend(split_items)
            if len(next_parts) > 1:
                parts = next_parts
                break

        clauses: list[dict[str, Any]] = []
        for index, part in enumerate(parts, start=1):
            title, content = self._title_and_content(part, template_name, index)
            clauses.append(
                {
                    "id": f"clause_{uuid4().hex[:16]}",
                    "document_id": document_id,
                    "doc_type": "template",
                    "template_id": template_id,
                    "template_name": template_name,
                    "category_lv1": category_lv1,
                    "category_lv2": category_lv2,
                    "clause_no": str(index),
                    "title": title,
                    "clause_type": self._infer_clause_type(title, content),
                    "content": content,
                    "page_start": page_start,
                    "page_end": page_end,
                    "status": "effective",
                    "effective_ts": effective_ts,
                    "abolish_ts": abolish_ts,
                    "risk_tags": self._risk_tags(title, content),
                }
            )
        return clauses

    @staticmethod
    def _title_and_content(part: str, fallback_title: str, index: int) -> tuple[str, str]:
        lines = [line.strip() for line in part.splitlines() if line.strip()]
        if not lines:
            return f"{fallback_title}-{index}", ""
        title = lines[0][:120]
        content = clean_text("\n".join(lines[1:]) if len(lines) > 1 else lines[0])
        return title, content

    @staticmethod
    def _infer_clause_type(title: str, content: str) -> str:
        text = f"{title}\n{content}"
        mapping = {
            "payment": ["付款", "支付", "价款"],
            "invoice": ["发票", "税率", "含税"],
            "acceptance": ["验收", "检验", "质量标准"],
            "breach": ["违约责任", "违约"],
            "dispute": ["争议解决", "仲裁", "诉讼"],
            "confidentiality": ["保密"],
            "termination": ["解除", "终止"],
        }
        for clause_type, keywords in mapping.items():
            if any(keyword in text for keyword in keywords):
                return clause_type
        return "general"

    @staticmethod
    def _risk_tags(title: str, content: str) -> list[str]:
        text = f"{title}\n{content}"
        tags: list[str] = []
        if any(keyword in text for keyword in ["付款", "预付款", "支付"]):
            tags.append("payment")
        if any(keyword in text for keyword in ["发票", "税率", "含税", "不含税"]):
            tags.append("invoice")
        if "争议解决" in text or "仲裁" in text or "诉讼" in text:
            tags.append("dispute")
        if "违约" in text:
            tags.append("breach")
        return tags
