from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypeVar

from app.config import Settings
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

T = TypeVar("T")


class ContractParserAgent:
    def __init__(self, qwen_service: QwenService, settings: Settings) -> None:
        self.qwen_service = qwen_service
        self.settings = settings
        self.parallelism = max(1, settings.qwen_parallel_requests)
        self.section_batch_size = max(2, settings.section_batch_size)
        self.section_batch_overlap = max(0, settings.section_batch_overlap)
        self.clause_batch_size = max(2, settings.clause_batch_size)
        self.key_fact_batch_size = max(3, settings.key_fact_batch_size)

    def derive_section_hints(self, pages: list[ContractPage]) -> list[ContractSection]:
        hints: list[ContractSection] = []
        seen_titles: set[str] = set()
        for page in pages:
            for block in page.blocks[:12]:
                title = self._clean(block.text)
                if not title or title in seen_titles or not self._is_likely_heading(title):
                    continue
                seen_titles.add(title)
                hints.append(
                    ContractSection(
                        id=f"hint_{len(hints) + 1:03d}",
                        title=title[:60],
                        level=1,
                        page=page.page,
                        summary=title[:120],
                        confidence=0.6,
                        evidenceId=None,
                    )
                )
                if len(hints) >= 24:
                    return hints
        return hints

    async def reconstruct_sections(self, pages: list[ContractPage]) -> list[ContractSection]:
        derived_sections = self._derive_sections_locally(pages)
        if self._derived_sections_are_sufficient(derived_sections, pages):
            return derived_sections

        if len(pages) <= max(self.section_batch_size * 3, 12):
            raw_sections = await self._request_sections(pages)
        else:
            batches = self._page_batches(
                pages=pages,
                batch_size=self.section_batch_size,
                overlap=self.section_batch_overlap,
            )
            batch_results = await self._gather_limited(
                [self._request_sections(batch) for batch in batches],
                limit=min(self.parallelism, len(batches)),
            )
            merged_candidates: list[dict[str, Any]] = []
            for batch in batch_results:
                merged_candidates.extend(batch)
            raw_sections = await self._merge_section_candidates(merged_candidates)

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
        return sections or derived_sections

    async def identify_clauses(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
    ) -> list[ClauseTag]:
        page_batches = self._page_batches(pages=pages, batch_size=self.clause_batch_size, overlap=0)
        tasks = [self._request_clauses(batch, sections) for batch in page_batches]
        raw_batches = await self._gather_limited(tasks, limit=min(self.parallelism, len(tasks)))
        raw_clauses: list[dict[str, Any]] = []
        for batch in raw_batches:
            raw_clauses.extend(batch)

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
        return self._dedupe_clauses(clauses)

    async def extract_key_facts(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
    ) -> list[KeyFact]:
        derived_facts = self._derive_key_facts_from_clauses(clauses)
        if self._derived_facts_are_sufficient(derived_facts):
            return self._dedupe_key_facts(derived_facts)

        clause_batches = self._chunk_items(clauses, self.key_fact_batch_size)
        raw_batches = await self._gather_limited(
            [self._request_key_facts(batch) for batch in clause_batches],
            limit=min(self.parallelism, len(clause_batches)),
        )
        raw_facts: list[dict[str, Any]] = []
        for batch in raw_batches:
            raw_facts.extend(batch)
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
            merged_facts = self._dedupe_key_facts(derived_facts + facts)
            return merged_facts
        return self._dedupe_key_facts(derived_facts)

    async def _request_sections(self, pages: list[ContractPage]) -> list[dict[str, Any]]:
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
            timeout=120,
        )
        return self._pick_first_array(
            payload,
            ["sections", "chapterTree", "chapter_tree", "\u7ae0\u8282", "\u7ae0\u8282\u6811"],
        )

    async def _merge_section_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact_candidates = []
        seen: set[tuple[str, int]] = set()
        for item in candidates:
            title = self._clean(item.get("title") or item.get("heading") or item.get("name"))
            page = self._safe_int(item.get("page")) or 1
            key = (title, page)
            if not title or key in seen:
                continue
            seen.add(key)
            compact_candidates.append(
                {
                    "title": title,
                    "level": self._safe_int(item.get("level")) or 1,
                    "page": page,
                    "summary": self._clean(item.get("summary") or item.get("snippet") or item.get("text"))[:160],
                    "confidence": item.get("confidence"),
                    "evidenceText": self._clean(
                        item.get("evidenceText") or item.get("snippet") or item.get("text") or item.get("rawText")
                    )[:200],
                }
            )

        if len(compact_candidates) <= 1:
            return compact_candidates

        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "You consolidate candidate contract sections from multiple page batches. "
                "Merge duplicates, keep the original document order, and preserve real section titles only."
            ),
            user_prompt=(
                f"Section candidates:\n{json.dumps(compact_candidates, ensure_ascii=False)}\n"
                "Return a JSON object with a top-level `sections` array."
            ),
            schema={"type": "object"},
            timeout=90,
        )
        merged = self._pick_first_array(
            payload,
            ["sections", "chapterTree", "chapter_tree", "\u7ae0\u8282", "\u7ae0\u8282\u6811"],
        )
        return merged or compact_candidates

    async def _request_clauses(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
    ) -> list[dict[str, Any]]:
        page_numbers = {page.page for page in pages}
        section_payload = [
            {
                "id": item.id,
                "title": item.title,
                "level": item.level,
                "page": item.page,
                "summary": item.summary,
            }
            for item in sections
            if item.page in page_numbers
        ][:40]
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
            timeout=120,
        )
        raw_clauses = self._pick_first_array(
            payload,
            ["clauses", "clauseTags", "clause_tags", "\u6761\u6b3e", "\u6761\u6b3e\u6807\u7b7e"],
        )
        if not raw_clauses:
            raw_clauses = self._clauses_from_structured_payload(payload)
        return raw_clauses

    async def _request_key_facts(self, clauses: list[ClauseTag]) -> list[dict[str, Any]]:
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
            timeout=90,
        )
        return self._pick_first_array(
            payload,
            ["keyFacts", "facts", "key_facts", "\u5173\u952e\u4fe1\u606f"],
        )

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

        party_pattern = re.compile(r"(\u7532\u65b9|\u4e59\u65b9)(?:\u540d\u79f0)?[:\uff1a]\s*([^\n\uff0c\u3002,\uff1b;]{2,60})")
        party_alt_patterns = {
            "\u7532\u65b9": re.compile(r"\u7532\u65b9(?:\u4e3a|\u662f)?([^\n\uff0c\u3002,\uff1b;]{2,60})"),
            "\u4e59\u65b9": re.compile(r"\u4e59\u65b9(?:\u4e3a|\u662f)?([^\n\uff0c\u3002,\uff1b;]{2,60})"),
        }
        amount_pattern = re.compile(
            r"(?:\u4eba\u6c11\u5e01|\u5408\u540c\u603b\u989d|\u603b\u91d1\u989d|\u91d1\u989d)[^0-9]{0,8}([0-9][0-9,\uff0c.]*(?:\u5143|\u4e07\u5143)?)"
        )

        for clause in clauses:
            if clause.label == "\u7532\u4e59\u65b9\u4fe1\u606f":
                matched_party_labels: set[str] = set()
                for match in party_pattern.finditer(clause.rawText):
                    add_fact(
                        label=match.group(1),
                        value=match.group(2),
                        page=clause.page,
                        confidence=clause.confidence,
                        evidence_id=clause.evidenceId,
                    )
                    matched_party_labels.add(match.group(1))
                for label, pattern in party_alt_patterns.items():
                    if label in matched_party_labels:
                        continue
                    alt_match = pattern.search(clause.rawText)
                    if alt_match:
                        add_fact(
                            label=label,
                            value=alt_match.group(1),
                            page=clause.page,
                            confidence=clause.confidence,
                            evidence_id=clause.evidenceId,
                        )
                add_fact("\u7532\u4e59\u65b9\u4fe1\u606f", clause.summary or clause.rawText[:120], clause.page, clause.confidence, clause.evidenceId)
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
            elif clause.label == "\u5c65\u7ea6\u671f\u9650":
                add_fact("\u5c65\u7ea6\u671f\u9650", clause.summary or clause.rawText[:80], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u670d\u52a1/\u91c7\u8d2d/\u5de5\u7a0b\u5185\u5bb9":
                add_fact("\u670d\u52a1/\u91c7\u8d2d/\u5de5\u7a0b\u5185\u5bb9", clause.summary or clause.rawText[:120], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u6743\u5229\u4e49\u52a1":
                add_fact("\u6743\u5229\u4e49\u52a1", clause.summary or clause.rawText[:120], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u8fdd\u7ea6\u8d23\u4efb":
                add_fact("\u8fdd\u7ea6\u8d23\u4efb", clause.summary or clause.rawText[:120], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u9644\u4ef6\u6761\u6b3e":
                add_fact("\u9644\u4ef6\u6761\u6b3e", clause.summary or clause.rawText[:80], clause.page, clause.confidence, clause.evidenceId)
            elif clause.label == "\u5176\u4ed6\u91cd\u8981\u6761\u6b3e":
                add_fact("\u5408\u540c\u4efd\u6570\u53ca\u6cd5\u5f8b\u6548\u529b", clause.summary or clause.rawText[:120], clause.page, clause.confidence, clause.evidenceId)

        unique: dict[tuple[str, str, int], KeyFact] = {}
        for fact in facts:
            unique[(fact.label, fact.value, fact.page)] = fact
        return list(unique.values())

    def _derive_sections_locally(self, pages: list[ContractPage]) -> list[ContractSection]:
        derived: list[ContractSection] = []
        seen: set[tuple[int, str]] = set()
        for page in pages:
            for block in page.blocks[:24]:
                candidates = self._extract_heading_candidates(block.text)
                for title in candidates:
                    key = (page.page, title)
                    if key in seen:
                        continue
                    seen.add(key)
                    derived.append(
                        ContractSection(
                            id=f"section_{len(derived) + 1:03d}",
                            title=title,
                            level=self._infer_heading_level(title),
                            page=page.page,
                            summary=self._build_section_summary(block.text, title),
                            confidence=0.74 if len(title) <= 28 else 0.68,
                            evidenceId=None,
                        )
                    )
                    if len(derived) >= 24:
                        return derived
        return derived

    @staticmethod
    def _extract_heading_candidates(text: str) -> list[str]:
        source = ContractParserAgent._clean(text)
        if not source:
            return []

        candidates: list[str] = []
        if len(source) <= 36 and ContractParserAgent._is_heading_candidate(source):
            candidates.append(ContractParserAgent._normalize_heading_candidate(source))

        patterns = [
            re.compile(r"(第[一二三四五六七八九十百零〇0-9]+[章节条][：:]?[^\n。；;]{0,32})"),
            re.compile(r"([一二三四五六七八九十]+、[^\n。；;]{0,28})"),
            re.compile(r"([0-9]+[.、][^\n。；;]{0,28})"),
            re.compile(r"([（(][0-9一二三四五六七八九十]+[)）][^\n。；;]{0,24})"),
        ]
        for pattern in patterns:
            for match in pattern.finditer(source):
                candidate = ContractParserAgent._normalize_heading_candidate(match.group(1))
                if ContractParserAgent._is_heading_candidate(candidate):
                    candidates.append(candidate)

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            unique.append(candidate)
        return unique

    @staticmethod
    def _normalize_heading_candidate(text: str) -> str:
        cleaned = ContractParserAgent._clean(text).strip("：:，,；;。. ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        if "扫描全能王" in cleaned:
            return ""
        return cleaned[:40]

    @staticmethod
    def _is_heading_candidate(text: str) -> bool:
        compact = ContractParserAgent._clean(text)
        if not compact or len(compact) < 3 or len(compact) > 40:
            return False
        if any(marker in compact for marker in ("扫描全能王", "填写说明", "合同登记机构", "经办人")):
            return False
        if re.fullmatch(r"[0-9A-Za-z\-_/：: ]+", compact):
            return False
        if re.match(r"^[0-9]+[.、]", compact):
            remainder = re.sub(r"^[0-9]+[.、]", "", compact, count=1)
            if not re.search(r"[\u4e00-\u9fff]{2,}", remainder):
                return False
            if re.match(r"^[0-9A-Za-z]", remainder):
                return False
        if re.match(r"^[（(][0-9一二三四五六七八九十]+[)）]", compact):
            remainder = re.sub(r"^[（(][0-9一二三四五六七八九十]+[)）]", "", compact, count=1)
            if not re.search(r"[\u4e00-\u9fff]{2,}", remainder):
                return False
        if sum(char.isdigit() for char in compact) >= max(4, len(compact) // 3) and not any(
            keyword in compact for keyword in ("合同", "服务", "付款", "验收", "责任", "保密", "争议", "期限", "内容")
        ):
            return False
        heading_patterns = (
            r"^第[一二三四五六七八九十百零〇0-9]+[章节条]",
            r"^[一二三四五六七八九十]+、",
            r"^[0-9]+[.、]",
            r"^[（(][0-9一二三四五六七八九十]+[)）]",
        )
        return any(re.match(pattern, compact) for pattern in heading_patterns) or ContractParserAgent._is_likely_heading(compact)

    @staticmethod
    def _infer_heading_level(text: str) -> int:
        compact = ContractParserAgent._clean(text)
        if re.match(r"^第[一二三四五六七八九十百零〇0-9]+章", compact):
            return 1
        if re.match(r"^第[一二三四五六七八九十百零〇0-9]+条", compact):
            return 1
        if re.match(r"^[一二三四五六七八九十]+、", compact):
            return 1
        if re.match(r"^[0-9]+[.、]", compact):
            return 2
        if re.match(r"^[（(][0-9一二三四五六七八九十]+[)）]", compact):
            return 3
        return 1

    @staticmethod
    def _build_section_summary(block_text: str, title: str) -> str:
        source = ContractParserAgent._clean(block_text)
        if not source:
            return title
        if source.startswith(title):
            source = source[len(title) :].strip("：:，,；;。 ")
        return source[:120] or title

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

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _chunk_items(items: list[T], batch_size: int) -> list[list[T]]:
        if not items:
            return []
        return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]

    @classmethod
    def _page_batches(
        cls,
        pages: list[ContractPage],
        batch_size: int,
        overlap: int,
    ) -> list[list[ContractPage]]:
        if not pages:
            return []
        step = max(1, batch_size - overlap)
        batches: list[list[ContractPage]] = []
        for index in range(0, len(pages), step):
            batch = pages[index : index + batch_size]
            if not batch:
                continue
            batches.append(batch)
            if index + batch_size >= len(pages):
                break
        return batches

    async def _gather_limited(self, coroutines: list[Any], limit: int) -> list[Any]:
        semaphore = asyncio.Semaphore(max(1, limit))

        async def run(coroutine: Any) -> Any:
            async with semaphore:
                return await coroutine

        return list(await asyncio.gather(*(run(coroutine) for coroutine in coroutines)))

    @staticmethod
    def _dedupe_clauses(clauses: list[ClauseTag]) -> list[ClauseTag]:
        best_by_key: dict[str, ClauseTag] = {}
        for clause in clauses:
            current = best_by_key.get(clause.label)
            if current is None:
                best_by_key[clause.label] = clause
                continue
            candidate_score = (clause.confidence, len(clause.rawText))
            current_score = (current.confidence, len(current.rawText))
            if candidate_score > current_score:
                best_by_key[clause.label] = clause
        deduped = list(best_by_key.values())
        deduped.sort(key=lambda item: (item.page, CLAUSE_LABELS.index(item.label) if item.label in CLAUSE_LABELS else 99))
        for index, clause in enumerate(deduped, start=1):
            clause.id = f"clause_{index:03d}"
        return deduped

    @staticmethod
    def _dedupe_key_facts(facts: list[KeyFact]) -> list[KeyFact]:
        best_by_key: dict[tuple[str, str, int], KeyFact] = {}
        for fact in facts:
            key = (fact.label, fact.value, fact.page)
            current = best_by_key.get(key)
            if current is None or fact.confidence > current.confidence:
                best_by_key[key] = fact
        deduped = list(best_by_key.values())
        deduped.sort(key=lambda item: (item.page, item.label, item.value))
        for index, fact in enumerate(deduped, start=1):
            fact.id = f"fact_{index:03d}"
        return deduped

    @staticmethod
    def _derived_sections_are_sufficient(sections: list[ContractSection], pages: list[ContractPage]) -> bool:
        if len(sections) < 6:
            return False
        covered_pages = {item.page for item in sections}
        if len(covered_pages) < min(3, len(pages)):
            return False
        top_level_count = sum(1 for item in sections if item.level <= 2)
        return top_level_count >= 5

    @staticmethod
    def _derived_facts_are_sufficient(facts: list[KeyFact]) -> bool:
        labels = {item.label for item in facts}
        coverage = {
            "\u7532\u65b9",
            "\u4e59\u65b9",
            "\u5408\u540c\u91d1\u989d",
            "\u4ed8\u6b3e\u6761\u4ef6",
            "\u9a8c\u6536\u6807\u51c6",
            "\u4e89\u8bae\u89e3\u51b3",
            "\u7532\u4e59\u65b9\u4fe1\u606f",
            "\u8d26\u6237\u4fe1\u606f",
        }
        return len(facts) >= 8 and len(labels & coverage) >= 5

    @staticmethod
    def _is_likely_heading(text: str) -> bool:
        compact = text.replace(" ", "").strip()
        if not compact:
            return False
        if len(compact) <= 28 and re.match(r"^[一二三四五六七八九十]+[、.．]", compact):
            return True
        if len(compact) <= 32 and re.match(r"^第[一二三四五六七八九十0-9]+[章节条款部分]", compact):
            return True
        heading_keywords = (
            "合同",
            "条款",
            "付款",
            "验收",
            "争议",
            "责任",
            "金额",
            "保密",
            "附件",
            "期限",
        )
        return len(compact) <= 24 and any(keyword in compact for keyword in heading_keywords)
