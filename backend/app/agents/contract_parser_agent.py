from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.contract import ClauseTag, ContractPage, ContractSection, KeyFact
from app.services.qwen_service import QwenService

CLAUSE_LABELS = [
    "\u5408\u540c\u57fa\u672c\u4fe1\u606f",
    "\u7532\u4e59\u65b9\u4fe1\u606f",
    "\u5408\u540c\u91d1\u989d",
    "\u4ed8\u6b3e\u6761\u4ef6",
    "\u5c65\u7ea6\u671f\u9650",
    "\u670d\u52a1/\u91c7\u8d2d/\u5de5\u7a0b\u5185\u5bb9",
    "\u9a8c\u6536\u6807\u51c6",
    "\u8fdd\u7ea6\u8d23\u4efb",
    "\u6743\u5229\u4e49\u52a1",
    "\u4fdd\u5bc6\u6761\u6b3e",
    "\u4e89\u8bae\u89e3\u51b3",
    "\u8d26\u6237\u4fe1\u606f",
    "\u9644\u4ef6\u6761\u6b3e",
    "\u5176\u4ed6\u91cd\u8981\u6761\u6b3e",
]


class ContractParserAgent:
    def __init__(self, qwen_service: QwenService) -> None:
        self.qwen_service = qwen_service

    async def reconstruct_sections(self, pages: list[ContractPage]) -> list[ContractSection]:
        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "You are an expert in contract structure reconstruction. "
                "The source document is a Chinese contract. Identify only sections that truly exist in the source text. "
                "For each section, return title, level, page, summary, confidence, and a supporting text snippet. "
                "If the section boundary is unclear, lower the confidence instead of inventing sections."
            ),
            user_prompt=(
                f"Contract page digest:\n{json.dumps(self._pages_payload(pages), ensure_ascii=False)}\n"
                "Return a JSON object. Prefer a top-level `sections` array."
            ),
            schema={"type": "object"},
            timeout=180,
        )

        raw_sections = self._pick_first_array(
            payload,
            ["sections", "chapterTree", "chapter_tree", "\u7ae0\u8282", "\u7ae0\u8282\u6811"],
        )
        sections: list[ContractSection] = []
        for index, item in enumerate(raw_sections, start=1):
            title = self._clean(item.get("title") or item.get("heading") or item.get("name"))
            if not title:
                continue
            evidence_text = self._clean(
                item.get("evidenceText")
                or item.get("snippet")
                or item.get("text")
                or item.get("rawText")
            )
            page = self._coerce_page(item.get("page"), pages, evidence_text)
            sections.append(
                ContractSection(
                    id=self._clean(item.get("id")) or f"section_{index:03d}",
                    title=title,
                    level=self._coerce_level(item.get("level")),
                    page=page,
                    summary=self._clean(item.get("summary")) or evidence_text[:120] or f"{title} related section",
                    confidence=self._clamp_confidence(item.get("confidence")),
                    evidenceId=None,
                )
            )
        return sections

    async def identify_clauses(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
    ) -> list[ClauseTag]:
        section_payload = [
            {
                "id": item.id,
                "title": item.title,
                "level": item.level,
                "page": item.page,
                "summary": item.summary,
            }
            for item in sections[:40]
        ]
        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "You are an expert at identifying key clauses in Chinese contracts for audit and risk review. "
                f"Only use these labels: {', '.join(CLAUSE_LABELS)}. "
                "For each clause, return label, title, summary, rawText, page, confidence, and needHumanReview. "
                "Do not invent clauses that do not exist."
            ),
            user_prompt=(
                f"Contract page digest:\n{json.dumps(self._pages_payload(pages), ensure_ascii=False)}\n"
                f"Recognized sections:\n{json.dumps(section_payload, ensure_ascii=False)}\n"
                "Return a JSON object. Prefer a top-level `clauses` array. "
                "If you prefer a structured object keyed by label, only use the allowed labels as top-level keys."
            ),
            schema={"type": "object"},
            timeout=180,
        )

        raw_clauses = self._pick_first_array(
            payload,
            ["clauses", "clauseTags", "clause_tags", "\u6761\u6b3e", "\u6761\u6b3e\u6807\u7b7e"],
        )
        if not raw_clauses:
            raw_clauses = self._clauses_from_structured_payload(payload)

        clauses: list[ClauseTag] = []
        for index, item in enumerate(raw_clauses, start=1):
            label = self._normalize_label(item.get("label") or item.get("tag") or item.get("type"))
            raw_text = self._clean(item.get("rawText") or item.get("text") or item.get("quote") or item.get("excerpt"))
            summary = self._clean(item.get("summary")) or raw_text[:140]
            if not label or not raw_text:
                continue
            page = self._coerce_page(item.get("page"), pages, raw_text)
            evidence_id = self._clean(item.get("evidenceId")) or self._locate_evidence_id(pages, page, raw_text)
            clauses.append(
                ClauseTag(
                    id=self._clean(item.get("id")) or f"clause_{index:03d}",
                    label=label,
                    title=self._clean(item.get("title")) or label,
                    summary=summary,
                    rawText=raw_text,
                    page=page,
                    confidence=self._clamp_confidence(item.get("confidence")),
                    evidenceId=evidence_id or f"evidence_clause_{index:03d}",
                    needHumanReview=self._to_bool(item.get("needHumanReview") or item.get("need_human_review")),
                    relatedAuditFocusIds=[],
                )
            )
        return clauses

    async def extract_key_facts(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
    ) -> list[KeyFact]:
        clause_payload = [
            {
                "id": item.id,
                "label": item.label,
                "title": item.title,
                "summary": item.summary,
                "rawText": item.rawText[:500],
                "page": item.page,
                "confidence": item.confidence,
            }
            for item in clauses[:60]
        ]

        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "You extract key facts from Chinese contracts. "
                "Focus on parties, contract amount, payment conditions, performance period, acceptance standard, "
                "dispute resolution, and account information. "
                "For each fact, return label, value, page, confidence, and optional notes. "
                "Do not invent facts that are not supported by the clauses."
            ),
            user_prompt=(
                f"Recognized clauses:\n{json.dumps(clause_payload, ensure_ascii=False)}\n"
                "Return a JSON object. Prefer a top-level `keyFacts` array."
            ),
            schema={"type": "object"},
            timeout=120,
        )

        raw_facts = self._pick_first_array(
            payload,
            ["keyFacts", "facts", "key_facts", "\u5173\u952e\u4fe1\u606f"],
        )
        facts: list[KeyFact] = []
        for index, item in enumerate(raw_facts, start=1):
            label = self._clean(item.get("label") or item.get("name"))
            value = self._clean(item.get("value") or item.get("content"))
            if not label or not value:
                continue
            page = self._coerce_page(item.get("page"), pages, value)
            facts.append(
                KeyFact(
                    id=self._clean(item.get("id")) or f"fact_{index:03d}",
                    label=label,
                    value=value,
                    page=page,
                    confidence=self._clamp_confidence(item.get("confidence")),
                    evidenceId=self._clean(item.get("evidenceId")) or self._locate_evidence_id(pages, page, value),
                    notes=self._clean(item.get("notes") or item.get("note") or item.get("remark")) or None,
                )
            )

        if facts:
            return facts
        return self._derive_key_facts_from_clauses(clauses)

    @staticmethod
    def _clauses_from_structured_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        clauses: list[dict[str, Any]] = []
        for label in CLAUSE_LABELS:
            if label not in payload:
                continue
            value = payload.get(label)
            raw_text = ContractParserAgent._stringify_clause_value(value)
            if not raw_text:
                continue
            clauses.append(
                {
                    "id": f"clause_{len(clauses) + 1:03d}",
                    "label": label,
                    "title": label,
                    "summary": raw_text[:140],
                    "rawText": raw_text,
                    "confidence": 0.82,
                    "needHumanReview": False,
                }
            )
        return clauses

    @staticmethod
    def _pages_payload(pages: list[ContractPage]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for page in pages:
            blocks = page.blocks[:40]
            block_summaries = [{"id": block.id, "text": block.text[:120]} for block in blocks if block.text.strip()]
            page_text = "\n".join(block.text.strip() for block in blocks if block.text.strip())[:1800]
            payload.append(
                {
                    "page": page.page,
                    "title": page.title,
                    "text": page_text,
                    "blocks": block_summaries,
                }
            )
        return payload

    @staticmethod
    def _pick_first_array(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _normalize_label(label: Any) -> str:
        text = str(label or "").strip()
        if not text:
            return ""
        alias_map = {
            "\u5408\u540c\u4e3b\u4f53": "\u7532\u4e59\u65b9\u4fe1\u606f",
            "\u4e3b\u4f53\u4fe1\u606f": "\u7532\u4e59\u65b9\u4fe1\u606f",
            "\u4ed8\u6b3e\u65b9\u5f0f": "\u4ed8\u6b3e\u6761\u4ef6",
            "\u4ed8\u6b3e\u6761\u6b3e": "\u4ed8\u6b3e\u6761\u4ef6",
            "\u91d1\u989d": "\u5408\u540c\u91d1\u989d",
            "\u670d\u52a1\u5185\u5bb9": "\u670d\u52a1/\u91c7\u8d2d/\u5de5\u7a0b\u5185\u5bb9",
            "\u91c7\u8d2d\u5185\u5bb9": "\u670d\u52a1/\u91c7\u8d2d/\u5de5\u7a0b\u5185\u5bb9",
            "\u5de5\u7a0b\u5185\u5bb9": "\u670d\u52a1/\u91c7\u8d2d/\u5de5\u7a0b\u5185\u5bb9",
            "\u4fdd\u5bc6": "\u4fdd\u5bc6\u6761\u6b3e",
            "\u4e89\u8bae": "\u4e89\u8bae\u89e3\u51b3",
            "\u8d26\u53f7\u4fe1\u606f": "\u8d26\u6237\u4fe1\u606f",
            "\u8d26\u6237": "\u8d26\u6237\u4fe1\u606f",
            "\u9644\u4ef6": "\u9644\u4ef6\u6761\u6b3e",
        }
        if text in CLAUSE_LABELS:
            return text
        return alias_map.get(text, "\u5176\u4ed6\u91cd\u8981\u6761\u6b3e")

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.72
        return max(0.01, min(score, 0.99))

    @staticmethod
    def _clean(value: Any) -> str:
        text = str(value or "").replace("\u3000", " ").replace("\r", "\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines).strip()

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y", "\u662f"}
        return bool(value)

    @staticmethod
    def _coerce_level(value: Any) -> int:
        try:
            level = int(value)
        except Exception:
            level = 1
        return max(1, min(level, 6))

    @staticmethod
    def _coerce_page(value: Any, pages: list[ContractPage], fallback_text: str) -> int:
        try:
            page = int(value)
            if any(item.page == page for item in pages):
                return page
        except Exception:
            pass
        located = ContractParserAgent._locate_page_by_text(pages, fallback_text)
        return located or (pages[0].page if pages else 1)

    @staticmethod
    def _locate_page_by_text(pages: list[ContractPage], target_text: str) -> int | None:
        text = ContractParserAgent._clean(target_text)
        if not text:
            return None
        text_variants = {text, text.replace(" ", ""), text[:48].replace(" ", "")}
        for page in pages:
            page_text = "\n".join(block.text for block in page.blocks)
            compact = page_text.replace(" ", "")
            if any(variant and (variant in page_text or variant in compact) for variant in text_variants):
                return page.page
        return None

    @staticmethod
    def _locate_evidence_id(pages: list[ContractPage], page_number: int, target_text: str) -> str | None:
        text = ContractParserAgent._clean(target_text)
        if not text:
            return None
        for page in pages:
            if page.page != page_number:
                continue
            compact_target = text.replace(" ", "")
            for block in page.blocks:
                block_text = ContractParserAgent._clean(block.text)
                if not block_text:
                    continue
                if text in block_text or compact_target in block_text.replace(" ", ""):
                    return block.id
        return None

    @staticmethod
    def _derive_key_facts_from_clauses(clauses: list[ClauseTag]) -> list[KeyFact]:
        facts: list[KeyFact] = []

        def add_fact(
            label: str,
            value: str,
            page: int,
            confidence: float,
            evidence_id: str | None,
            notes: str | None = None,
        ) -> None:
            if not value.strip():
                return
            facts.append(
                KeyFact(
                    id=f"fact_{len(facts) + 1:03d}",
                    label=label,
                    value=value.strip(),
                    page=page,
                    confidence=max(0.5, min(confidence, 0.95)),
                    evidenceId=evidence_id,
                    notes=notes,
                )
            )

        party_pattern = re.compile(r"(\u7532\u65b9|\u4e59\u65b9)[:\uff1a]\s*([^\n\uff0c\u3002,\uff1b;]{2,40})")
        amount_pattern = re.compile(
            r"(?:\u4eba\u6c11\u5e01|\u5408\u540c\u603b\u989d|\u603b\u91d1\u989d|\u91d1\u989d)[^0-9]{0,8}([0-9][0-9,\uff0c.]*(?:\u5143|\u4e07\u5143)?)"
        )

        for clause in clauses:
            if clause.label == "\u7532\u4e59\u65b9\u4fe1\u606f":
                for match in party_pattern.finditer(clause.rawText):
                    add_fact(
                        label=match.group(1),
                        value=match.group(2),
                        page=clause.page,
                        confidence=clause.confidence,
                        evidence_id=clause.evidenceId,
                    )
            elif clause.label == "\u5408\u540c\u91d1\u989d":
                match = amount_pattern.search(clause.rawText)
                if match:
                    add_fact(
                        label="\u5408\u540c\u91d1\u989d",
                        value=match.group(1),
                        page=clause.page,
                        confidence=clause.confidence,
                        evidence_id=clause.evidenceId,
                    )
            elif clause.label == "\u4ed8\u6b3e\u6761\u4ef6":
                add_fact("\u4ed8\u6b3e\u6761\u4ef6", clause.summary or clause.rawText[:80], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u9a8c\u6536\u6807\u51c6":
                add_fact("\u9a8c\u6536\u6807\u51c6", clause.summary or clause.rawText[:80], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u4e89\u8bae\u89e3\u51b3":
                add_fact("\u4e89\u8bae\u89e3\u51b3", clause.summary or clause.rawText[:80], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u8d26\u6237\u4fe1\u606f":
                add_fact("\u8d26\u6237\u4fe1\u606f", clause.summary or clause.rawText[:80], clause.page, clause.confidence, clause.evidenceId)

        unique: dict[tuple[str, str, int], KeyFact] = {}
        for fact in facts:
            unique[(fact.label, fact.value, fact.page)] = fact
        return list(unique.values())

    @staticmethod
    def _stringify_clause_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return ContractParserAgent._clean(value)
        if isinstance(value, list):
            parts = [ContractParserAgent._stringify_clause_value(item) for item in value]
            return "\uff1b".join(part for part in parts if part)
        if isinstance(value, dict):
            parts: list[str] = []
            for key, item in value.items():
                item_text = ContractParserAgent._stringify_clause_value(item)
                if item_text:
                    parts.append(f"{key}\uff1a{item_text}")
            return "\uff1b".join(parts)
        return ContractParserAgent._clean(json.dumps(value, ensure_ascii=False))
