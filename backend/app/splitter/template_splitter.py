from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.parser.text_cleaner import clean_text


class TemplateSplitter:
    template_line_pattern = re.compile(r"^(\d+\.\d+\.\d+)\s*(.+?)\.{2,}\s*(\d+)$")
    category_lv2_pattern = re.compile(r"^(\d+\.\d+)\s*(.+)$")
    category_lv1_pattern = re.compile(r"^[一二三四五六七八九十]+、\s*(.+类)$")

    def extract_catalog(self, parsed: dict) -> list[dict[str, Any]]:
        catalog_pages = parsed["pages"][: min(8, len(parsed["pages"]))]
        current_lv1: str | None = None
        current_lv2: str | None = None
        catalog: list[dict[str, Any]] = []
        for page in catalog_pages:
            for raw_line in page["text"].splitlines():
                line = clean_text(raw_line)
                compact = re.sub(r"\s+", "", line)
                if not compact:
                    continue
                match_lv1 = self.category_lv1_pattern.match(line) or self.category_lv1_pattern.match(compact)
                if match_lv1:
                    current_lv1 = match_lv1.group(1)
                    current_lv2 = None
                    continue
                match_lv2 = self.category_lv2_pattern.match(line)
                if match_lv2 and line.count(".") == 1:
                    current_lv2 = match_lv2.group(2)
                    continue
                match_template = self.template_line_pattern.match(line)
                if match_template:
                    template_code = match_template.group(1)
                    template_name = match_template.group(2)
                    start_page = int(match_template.group(3))
                    catalog.append(
                        {
                            "template_id": f"tpl_{template_code.replace('.', '_')}_{uuid4().hex[:6]}",
                            "template_name": template_name,
                            "category_lv1": current_lv1,
                            "category_lv2": current_lv2,
                            "catalog_page": start_page,
                        }
                    )
        return catalog

    def resolve_template_ranges(self, parsed: dict, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not catalog:
            return []
        offset = self._detect_page_offset(parsed, catalog)
        resolved: list[dict[str, Any]] = []
        for index, item in enumerate(catalog):
            start_page = item["catalog_page"] + offset
            next_start = (
                catalog[index + 1]["catalog_page"] + offset - 1
                if index + 1 < len(catalog)
                else parsed["page_count"]
            )
            resolved.append(
                {
                    **item,
                    "start_page": max(1, start_page),
                    "end_page": max(start_page, next_start),
                }
            )
        return resolved

    @staticmethod
    def template_text(parsed: dict, start_page: int, end_page: int) -> str:
        pages = [item["text"] for item in parsed["pages"] if start_page <= item["page"] <= end_page]
        return clean_text("\n\n".join(pages))

    @staticmethod
    def _detect_page_offset(parsed: dict, catalog: list[dict[str, Any]]) -> int:
        for item in catalog[:5]:
            expected_title = clean_text(item["template_name"])
            for page in parsed["pages"]:
                if page["page"] <= min(8, parsed["page_count"]):
                    continue
                if expected_title and expected_title in page["text"]:
                    return page["page"] - item["catalog_page"]
        return 0
