from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from app.config import Settings
from app.prompts.context import build_audit_config_prompt_context
from app.prompts.contract import (
    build_clause_semantic_prompt,
    build_key_fact_prompt,
    build_overview_text_prompt,
    build_overview_vl_prompt,
    build_section_semantic_prompt,
)
from app.schemas.contract import ClauseTag, ContractPage, ContractSection, KeyFact
from app.schemas.relation import AuditConfigType, RelationConfig
from app.services.qwen_service import QwenService

CLAUSE_LABELS = [
    "合同基本信息",
    "甲乙方信息",
    "合同金额",
    "付款条件",
    "履约期限",
    "服务/采购/工程内容",
    "验收标准",
    "违约责任",
    "权利义务",
    "保密条款",
    "争议解决",
    "账户信息",
    "附件条款",
    "其他重要条款",
]

DEFAULT_OVERVIEW_FACTS = {
    "合同编号": "未提取",
    "主体摘要": "待提取",
    "甲乙方信息": "待提取",
    "服务内容": "待提取",
}


class ContractParserAgent:
    def __init__(self, qwen_service: QwenService, settings: Settings) -> None:
        self.qwen_service = qwen_service
        self.parallelism = max(1, settings.qwen_parallel_requests)
        self.key_fact_batch_size = max(2, settings.key_fact_batch_size)

    async def reconstruct_sections(self, pages: list[ContractPage]) -> list[ContractSection]:
        items = await self._request_sections(pages)
        sections = self._build_sections_from_items(items, pages)
        if sections:
            return sections
        return self._derive_sections_locally(pages)

    async def identify_clauses(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
        relations: list[RelationConfig] | None = None,
    ) -> list[ClauseTag]:
        items = await self._request_clauses(pages, sections, relations or [])
        clauses = self._build_clauses_from_items(items, pages)
        if clauses:
            return self._dedupe_clauses(clauses)
        return self._dedupe_clauses(self._derive_clauses_locally(pages, sections))

    async def extract_key_facts(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
        relations: list[RelationConfig] | None = None,
    ) -> list[KeyFact]:
        requested_fields = self._extract_requested_fact_fields(relations or [])
        derived_facts = self._dedupe_key_facts(
            self._derive_key_facts_from_pages(pages) + self._derive_key_facts_from_clauses(clauses)
        )

        overview_task = self._request_overview_key_facts(pages, clauses)
        clause_batches = self._chunk_items(clauses, self.key_fact_batch_size)
        batch_tasks = [self._request_key_facts(batch, requested_fields) for batch in clause_batches]

        overview_result, raw_batches = await asyncio.gather(
            self._safe_list_call(overview_task),
            self._gather_limited(batch_tasks, min(self.parallelism, max(1, len(batch_tasks))))
            if batch_tasks
            else self._empty_batches(),
        )

        facts: list[KeyFact] = []
        for batch in raw_batches:
            for item in batch:
                fact = self._build_key_fact(item, pages)
                if fact:
                    facts.append(fact)

        merged = self._dedupe_key_facts(overview_result + derived_facts + facts)
        self._ensure_required_overview_facts(merged)
        return self._dedupe_key_facts(merged)

    async def _request_sections(self, pages: list[ContractPage]) -> list[dict[str, Any]]:
        prompt = build_section_semantic_prompt(self._pages_payload(pages))
        payload = await self.qwen_service.chat_json(
            system_prompt=prompt.system,
            user_prompt=prompt.user,
            schema={"type": "object"},
            timeout=120,
        )
        return self._pick_first_array(payload, ["sections", "chapterTree", "chapter_tree"])

    async def _request_clauses(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
        relations: list[RelationConfig],
    ) -> list[dict[str, Any]]:
        section_payload = [
            {
                "id": section.id,
                "title": section.title,
                "level": section.level,
                "page": section.page,
                "sortOrder": section.sortOrder,
                "sectionCode": section.sectionCode,
                "summary": section.summary,
            }
            for section in sections[:64]
        ]
        prompt = build_clause_semantic_prompt(
            page_payload=self._pages_payload(pages),
            section_payload=section_payload,
            clause_labels=CLAUSE_LABELS,
            relation_payload=build_audit_config_prompt_context(relations),
        )
        payload = await self.qwen_service.chat_json(
            system_prompt=prompt.system,
            user_prompt=prompt.user,
            schema={"type": "object"},
            timeout=150,
        )
        return self._pick_first_array(payload, ["clauses", "clauseTags", "clause_tags"])

    async def _request_key_facts(
        self,
        clauses: list[ClauseTag],
        requested_fields: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        clause_payload = [
            {
                "id": clause.id,
                "label": clause.label,
                "coreLabel": clause.coreLabel,
                "title": clause.title,
                "sectionTitle": clause.sectionTitle,
                "summary": clause.summary,
                "rawText": clause.rawText[:360],
                "references": clause.references,
                "structuredFields": clause.structuredFields,
                "page": clause.page,
                "confidence": clause.confidence,
            }
            for clause in clauses[:48]
        ]
        prompt = build_key_fact_prompt(clause_payload, requested_fields)
        payload = await self.qwen_service.chat_json(
            system_prompt=prompt.system,
            user_prompt=prompt.user,
            schema={"type": "object"},
            timeout=90,
        )
        return self._pick_first_array(payload, ["keyFacts", "facts", "key_facts"])

    async def _request_overview_key_facts(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
    ) -> list[KeyFact]:
        clause_payload = [
            {
                "id": clause.id,
                "label": clause.label,
                "summary": clause.summary,
                "page": clause.page,
                "rawText": clause.rawText[:360],
            }
            for clause in clauses[:12]
        ]
        page_payload = [
            {
                "page": page.page,
                "text": "\n".join(self._clean(block.text) for block in page.blocks[:32])[:2200],
            }
            for page in pages[:3]
        ]

        payload: dict[str, Any] | None = None
        first_page = pages[0] if pages else None
        first_page_image = Path(first_page.imageLocalPath) if first_page and first_page.imageLocalPath else None
        if first_page_image and first_page_image.exists():
            try:
                payload = await self.qwen_service.vision_json(
                    prompt=build_overview_vl_prompt(),
                    image_path=first_page_image,
                    schema={"type": "object"},
                    timeout=120,
                )
            except Exception:
                payload = None

        if payload is None:
            prompt = build_overview_text_prompt(page_payload, clause_payload)
            payload = await self.qwen_service.chat_json(
                system_prompt=prompt.system,
                user_prompt=prompt.user,
                schema={"type": "object"},
                timeout=90,
            )

        facts: list[KeyFact] = []
        for item in self._pick_first_array(payload, ["overviewFacts", "keyFacts", "facts"]):
            fact = self._build_key_fact(item, pages, force_overview_label=True)
            if fact:
                facts.append(fact)
        return facts

    def _build_sections_from_items(
        self,
        items: list[dict[str, Any]],
        pages: list[ContractPage],
    ) -> list[ContractSection]:
        sections: list[ContractSection] = []
        seen: set[tuple[int, str]] = set()
        for index, item in enumerate(items, start=1):
            title = self._clean(item.get("title") or item.get("heading") or item.get("name"))
            if not title:
                continue
            evidence_text = self._clean(item.get("evidenceText") or item.get("snippet") or title)
            page = self._coerce_page(item.get("page"), pages, evidence_text)
            key = (page, title)
            if key in seen:
                continue
            seen.add(key)
            sections.append(
                ContractSection(
                    id=f"section_{len(sections) + 1:03d}",
                    title=title,
                    level=self._coerce_level(item.get("level")),
                    page=page,
                    summary=self._compact_summary(self._clean(item.get("summary")) or evidence_text, 80),
                    confidence=self._clamp_confidence(item.get("confidence")),
                    sortOrder=self._coerce_sort_order(item.get("sortOrder"), index),
                    sectionCode=self._clean(item.get("sectionCode")) or self._extract_section_code(title),
                    sectionPath=self._clean(item.get("sectionPath")) or None,
                    blockIds=[],
                    evidenceId=None,
                )
            )
        sections.sort(key=lambda item: (item.page, item.sortOrder))
        for index, section in enumerate(sections, start=1):
            section.id = f"section_{index:03d}"
            section.sortOrder = index
        return sections

    def _build_clauses_from_items(
        self,
        items: list[dict[str, Any]],
        pages: list[ContractPage],
    ) -> list[ClauseTag]:
        clauses: list[ClauseTag] = []
        for index, item in enumerate(items, start=1):
            label = self._clean(item.get("label") or item.get("title"))
            if not label:
                continue
            core_label = self._normalize_core_label(item.get("coreLabel") or item.get("core_label") or label)
            raw_text = self._compact_summary(
                self._clean(item.get("rawText") or item.get("text") or item.get("quote")),
                260,
            )
            summary = self._compact_summary(self._clean(item.get("summary")) or raw_text, 80)
            page = self._coerce_page(item.get("page"), pages, raw_text or summary)
            references = self._normalize_reference_list(item.get("references"))
            structured_fields = self._normalize_structured_fields(item.get("structuredFields"))
            clauses.append(
                ClauseTag(
                    id=f"clause_{index:03d}",
                    label=label,
                    coreLabel=core_label,
                    labelSource=self._normalize_label_source(
                        item.get("labelSource") or item.get("label_source"),
                        label=label,
                        core_label=core_label,
                    ),
                    title=self._clean(item.get("title")) or label,
                    summary=summary,
                    rawText=raw_text or summary,
                    page=page,
                    confidence=self._clamp_confidence(item.get("confidence")),
                    sortOrder=self._coerce_sort_order(item.get("sortOrder"), index),
                    sectionTitle=self._clean(item.get("sectionTitle")) or None,
                    references=references,
                    structuredFields=structured_fields,
                    anchorText=(self._clean(item.get("anchorText")) or raw_text[:120]) if raw_text else None,
                    blockIds=[],
                    evidenceId="",
                    needHumanReview=self._to_bool(item.get("needHumanReview") or item.get("need_human_review")),
                    discoveryReason=self._clean(item.get("discoveryReason") or item.get("discovery_reason")) or None,
                    relatedAuditFocusIds=[],
                )
            )
        return clauses

    def _derive_sections_locally(self, pages: list[ContractPage]) -> list[ContractSection]:
        sections: list[ContractSection] = []
        for page in pages:
            for block in page.blocks:
                title = self._clean(block.text)
                if not title or not self._looks_like_heading(title):
                    continue
                sections.append(
                    ContractSection(
                        id=f"section_{len(sections) + 1:03d}",
                        title=title[:80],
                        level=self._infer_heading_level(title),
                        page=page.page,
                        summary=self._compact_summary(title, 80),
                        confidence=0.55,
                        sortOrder=len(sections) + 1,
                        sectionCode=self._extract_section_code(title),
                        sectionPath=None,
                    )
                )
        if sections:
            return sections
        if not pages:
            return []
        return [
            ContractSection(
                id="section_001",
                title="合同正文",
                level=1,
                page=pages[0].page,
                summary="未稳定识别出显式章节标题，建议人工复核。",
                confidence=0.35,
                sortOrder=1,
                sectionCode=None,
                sectionPath=None,
            )
        ]

    def _derive_clauses_locally(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
    ) -> list[ClauseTag]:
        keyword_map = {
            "甲乙方信息": ["甲方", "乙方", "委托方", "受托方"],
            "合同金额": ["合同金额", "总额", "人民币", "金额"],
            "付款条件": ["付款", "支付", "比例", "节点"],
            "履约期限": ["期限", "工期", "完成时间", "服务期"],
            "服务/采购/工程内容": ["服务内容", "工作内容", "技术服务", "采购内容", "工程内容"],
            "验收标准": ["验收", "交付", "成果", "标准"],
            "违约责任": ["违约", "赔偿", "责任", "逾期"],
            "争议解决": ["争议", "仲裁", "法院", "协商"],
            "账户信息": ["账户", "账号", "开户行", "银行"],
            "附件条款": ["附件", "附表", "补充协议"],
        }
        clauses: list[ClauseTag] = []
        for label, keywords in keyword_map.items():
            anchor = self._find_clause_anchor(pages, keywords)
            if anchor is None:
                continue
            page, block = anchor
            section_title = self._nearest_section_title(page.page, sections)
            clauses.append(
                ClauseTag(
                    id=f"clause_{len(clauses) + 1:03d}",
                    label=label,
                    coreLabel=label if label in CLAUSE_LABELS else "其他重要条款",
                    labelSource="core",
                    title=label,
                    summary=self._compact_summary(block.text, 80),
                    rawText=self._compact_summary(block.text, 260),
                    page=page.page,
                    confidence=0.5,
                    sortOrder=len(clauses) + 1,
                    sectionTitle=section_title,
                    references=self._extract_cross_references(block.text),
                    structuredFields={},
                    anchorText=self._compact_summary(block.text, 120),
                    blockIds=[],
                    evidenceId="",
                    needHumanReview=True,
                    discoveryReason="基于关键词和版面位置的本地兜底识别。",
                    relatedAuditFocusIds=[],
                )
            )
        return clauses

    def _build_key_fact(
        self,
        item: dict[str, Any],
        pages: list[ContractPage],
        force_overview_label: bool = False,
    ) -> KeyFact | None:
        label = self._clean(item.get("label") or item.get("name"))
        if force_overview_label:
            label = self._normalize_overview_label(label)
        if not label:
            return None

        value = self._sanitize_fact_value(label, self._clean(item.get("value") or item.get("content")))
        if not value:
            return None

        evidence_text = self._clean(item.get("evidenceText") or item.get("evidence") or value)
        page = self._coerce_page(item.get("page"), pages, evidence_text or value)
        return KeyFact(
            id=self._clean(item.get("id")) or f"fact_{label}_{page}",
            label=label,
            value=value,
            page=page,
            confidence=self._clamp_confidence(item.get("confidence")),
            evidenceId=self._clean(item.get("evidenceId")) or self._locate_evidence_id(pages, page, evidence_text),
            notes=self._clean(item.get("notes") or item.get("note") or item.get("remark")) or None,
        )

    def _extract_requested_fact_fields(self, relations: list[RelationConfig]) -> list[dict[str, str]]:
        requested: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in relations:
            if not item.enabled or item.configType != AuditConfigType.RULE_CHECK or not item.rulePayload:
                continue
            candidates = item.rulePayload.get("extractFields") or item.rulePayload.get("requiredFacts") or []
            if not isinstance(candidates, list):
                continue
            for entry in candidates:
                if isinstance(entry, str):
                    label = self._clean(entry)
                    description = ""
                elif isinstance(entry, dict):
                    label = self._clean(entry.get("label") or entry.get("name"))
                    description = self._clean(entry.get("description") or entry.get("prompt"))
                else:
                    continue
                if not label or label in seen:
                    continue
                seen.add(label)
                requested.append({"label": label, "description": description})
        return requested

    @staticmethod
    def _pages_payload(pages: list[ContractPage]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for page in pages:
            blocks = [ContractParserAgent._clean(block.text) for block in page.blocks[:40] if ContractParserAgent._clean(block.text)]
            payload.append({"page": page.page, "title": page.title, "text": "\n".join(blocks)[:5000]})
        return payload

    @staticmethod
    def _normalize_core_label(label: Any) -> str:
        text = str(label or "").strip()
        alias_map = {
            "合同主体": "甲乙方信息",
            "主体信息": "甲乙方信息",
            "付款方式": "付款条件",
            "付款条款": "付款条件",
            "金额": "合同金额",
            "服务内容": "服务/采购/工程内容",
            "采购内容": "服务/采购/工程内容",
            "工程内容": "服务/采购/工程内容",
            "保密": "保密条款",
            "争议": "争议解决",
            "账号信息": "账户信息",
            "账户": "账户信息",
            "附件": "附件条款",
        }
        if text in CLAUSE_LABELS:
            return text
        if text in alias_map:
            return alias_map[text]
        return "其他重要条款"

    @staticmethod
    def _normalize_label_source(label_source: Any, label: str = "", core_label: str = "") -> str:
        text = str(label_source or "").strip().lower()
        if text in {"agent_discovered", "agent"}:
            return "agent_discovered"
        if text in {"user_configured", "user"}:
            return "user_configured"
        if label and label != core_label and label not in CLAUSE_LABELS:
            return "agent_discovered"
        return "core"

    @staticmethod
    def _normalize_overview_label(label: str) -> str:
        compact = label.strip()
        alias_map = {
            "协议编号": "合同编号",
            "编号": "合同编号",
            "主体信息摘要": "主体摘要",
            "合同主体摘要": "主体摘要",
            "合同基本信息": "主体摘要",
            "合同主体信息": "甲乙方信息",
            "双方主体信息": "甲乙方信息",
            "主体信息": "甲乙方信息",
            "项目内容": "服务内容",
            "合同服务内容": "服务内容",
            "服务/采购/工程内容": "服务内容",
        }
        return alias_map.get(compact, compact)

    def _sanitize_fact_value(self, label: str, value: str) -> str:
        text = self._compact_summary(value, 120)
        if not text:
            return ""
        if label == "合同编号":
            text = self._extract_contract_number(text) or ""
            return text or "未提取"
        if label in {"主体摘要", "甲乙方信息", "服务内容"}:
            return self._compact_summary(text, 80) or "待提取"
        if label in {"付款条件", "履约期限", "验收标准", "争议解决", "账户信息"}:
            return self._compact_summary(text, 80)
        return text

    def _extract_contract_number(self, text: str) -> str | None:
        patterns = [
            re.compile(r"(?:合同|协议|项目)?(?:编号|备案号|合同编号|协议编号)\s*[:：]?\s*([A-Za-z0-9\u4e00-\u9fa5\\-_/().（）]{4,80})"),
            re.compile(r"\b([A-Z]{1,8}-\d{4,}[-A-Z0-9/]*)\b"),
            re.compile(r"\b(\d{2,}-\d{4,}[A-Za-z0-9-]*)\b"),
        ]
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            candidate = match.group(1).strip().strip("。；;,，")
            if self._looks_like_contract_number(candidate):
                return candidate
        return None

    @staticmethod
    def _looks_like_contract_number(text: str) -> bool:
        compact = text.strip()
        if len(compact) < 4:
            return False
        if "合同" in compact and not any(char.isdigit() for char in compact):
            return False
        return bool(re.search(r"[A-Za-z0-9]", compact))

    @staticmethod
    def _ensure_required_overview_facts(facts: list[KeyFact]) -> None:
        labels = {fact.label for fact in facts}
        for label, fallback in DEFAULT_OVERVIEW_FACTS.items():
            if label in labels:
                continue
            facts.append(
                KeyFact(
                    id=f"fact_placeholder_{len(facts) + 1:03d}",
                    label=label,
                    value=fallback,
                    page=1,
                    confidence=0.2,
                    evidenceId=None,
                    notes="模型未稳定识别到该字段。",
                )
            )

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
    def _compact_summary(value: str, limit: int) -> str:
        cleaned = ContractParserAgent._clean(value).replace("\n", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: max(8, limit - 1)].rstrip("，,；;：: ") + "…"

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y", "是"}
        return bool(value)

    @staticmethod
    def _coerce_level(value: Any) -> int:
        try:
            level = int(value)
        except Exception:
            level = 1
        return max(1, min(level, 6))

    @staticmethod
    def _coerce_sort_order(value: Any, fallback: int) -> int:
        try:
            return max(1, int(value))
        except Exception:
            return max(1, fallback)

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
        compact_target = text.replace(" ", "")
        for page in pages:
            page_text = "\n".join(block.text for block in page.blocks)
            compact_page = page_text.replace(" ", "")
            if text in page_text or compact_target in compact_page:
                return page.page
        return None

    @staticmethod
    def _locate_evidence_id(pages: list[ContractPage], page_number: int, target_text: str) -> str | None:
        text = ContractParserAgent._clean(target_text)
        if not text:
            return None
        compact_target = text.replace(" ", "")
        for page in pages:
            if page.page != page_number:
                continue
            for block in page.blocks:
                block_text = ContractParserAgent._clean(block.text)
                if not block_text:
                    continue
                if text in block_text or compact_target in block_text.replace(" ", ""):
                    return block.id
        return None

    @staticmethod
    def _derive_key_facts_from_pages(pages: list[ContractPage]) -> list[KeyFact]:
        facts: list[KeyFact] = []
        seen_values: set[str] = set()
        for page in pages[: min(len(pages), 4)]:
            for block in page.blocks[:80]:
                extracted = ContractParserAgent._extract_contract_number_static(block.text)
                if not extracted or extracted in seen_values:
                    continue
                seen_values.add(extracted)
                facts.append(
                    KeyFact(
                        id=f"fact_{len(facts) + 1:03d}",
                        label="合同编号",
                        value=extracted,
                        page=page.page,
                        confidence=0.88,
                        evidenceId=block.id,
                        notes="基于 OCR 原文块直接提取。",
                    )
                )
        return facts

    @staticmethod
    def _extract_contract_number_static(text: str) -> str | None:
        cleaned = ContractParserAgent._clean(text)
        patterns = [
            re.compile(r"(?:合同|协议|项目)?(?:编号|备案号|合同编号|协议编号)\s*[:：]?\s*([A-Za-z0-9\u4e00-\u9fa5\\-_/().（）]{4,80})"),
            re.compile(r"\b([A-Z]{1,8}-\d{4,}[-A-Z0-9/]*)\b"),
            re.compile(r"\b(\d{2,}-\d{4,}[A-Za-z0-9-]*)\b"),
        ]
        for pattern in patterns:
            match = pattern.search(cleaned)
            if not match:
                continue
            candidate = match.group(1).strip().strip("。；;,，")
            if ContractParserAgent._looks_like_contract_number(candidate):
                return candidate
        return None

    @staticmethod
    def _derive_key_facts_from_clauses(clauses: list[ClauseTag]) -> list[KeyFact]:
        facts: list[KeyFact] = []
        seen: set[tuple[str, str, int]] = set()
        party_pattern = re.compile(r"(甲方|乙方|委托方|受托方)\s*[（(]?\s*[^):：）]*[)）]?\s*[:：]?\s*([^\n（）()]{2,80})")
        amount_pattern = re.compile(r"(?:人民币|合同总额|总金额|金额)[^0-9]{0,8}([0-9][0-9,，.]*\s*(?:元|万元)?)")

        def add_fact(label: str, value: str, clause: ClauseTag, notes: str | None = None) -> None:
            clean_value = ContractParserAgent._clean(value)
            if not label or not clean_value:
                return
            key = (label, clean_value, clause.page)
            if key in seen:
                return
            seen.add(key)
            facts.append(
                KeyFact(
                    id=f"fact_{len(facts) + 1:03d}",
                    label=label,
                    value=clean_value,
                    page=clause.page,
                    confidence=clause.confidence,
                    evidenceId=clause.evidenceId or None,
                    notes=notes,
                )
            )

        for clause in clauses:
            clause_key = (clause.coreLabel or clause.label).strip()
            structured = clause.structuredFields or {}

            contract_number = structured.get("contractNumber")
            if contract_number:
                add_fact("合同编号", str(contract_number), clause, notes="来自条款结构化字段")

            if structured.get("serviceScope") and clause_key == "服务/采购/工程内容":
                add_fact("服务内容", str(structured.get("serviceScope")), clause, notes="来自条款结构化字段")

            if structured.get("totalAmount") and clause_key == "合同金额":
                add_fact("合同金额", str(structured.get("totalAmount")), clause, notes="来自条款结构化字段")

            if structured.get("paymentTrigger") and clause_key == "付款条件":
                add_fact("付款条件", str(structured.get("paymentTrigger")), clause, notes="来自条款结构化字段")

            if structured.get("implementationDays") and clause_key == "履约期限":
                add_fact("履约期限", str(structured.get("implementationDays")), clause, notes="来自条款结构化字段")

            if clause_key == "合同基本信息":
                number_match = ContractParserAgent._extract_contract_number_static(clause.rawText)
                if number_match:
                    add_fact("合同编号", number_match, clause)
                add_fact("主体摘要", clause.summary, clause)
            elif clause_key == "甲乙方信息":
                matched = False
                for match in party_pattern.finditer(clause.rawText):
                    add_fact(match.group(1), match.group(2), clause)
                    matched = True
                add_fact("甲乙方信息", clause.summary, clause)
                if not matched:
                    add_fact("主体摘要", clause.summary, clause, notes="主体名称建议人工复核")
            elif clause_key == "合同金额":
                match = amount_pattern.search(clause.rawText)
                add_fact("合同金额", match.group(1) if match else clause.summary, clause)
            elif clause_key == "付款条件":
                add_fact("付款条件", clause.summary, clause)
            elif clause_key == "履约期限":
                add_fact("履约期限", clause.summary, clause)
            elif clause_key == "验收标准":
                add_fact("验收标准", clause.summary, clause)
            elif clause_key == "争议解决":
                add_fact("争议解决", clause.summary, clause)
            elif clause_key == "账户信息":
                add_fact("账户信息", clause.summary, clause)
            elif clause_key == "服务/采购/工程内容":
                add_fact("服务内容", clause.summary, clause)
        return facts

    @staticmethod
    def _dedupe_clauses(clauses: list[ClauseTag]) -> list[ClauseTag]:
        best_by_key: dict[tuple[str, int], ClauseTag] = {}
        for clause in clauses:
            dedupe_key = (clause.label if clause.labelSource == "agent_discovered" else clause.coreLabel, clause.page)
            current = best_by_key.get(dedupe_key)
            if current is None:
                best_by_key[dedupe_key] = clause
                continue
            candidate_score = (clause.confidence, len(clause.rawText))
            current_score = (current.confidence, len(current.rawText))
            if candidate_score > current_score:
                best_by_key[dedupe_key] = clause
        deduped = list(best_by_key.values())
        deduped.sort(key=lambda item: (item.page, item.sortOrder, item.label))
        for index, clause in enumerate(deduped, start=1):
            clause.id = f"clause_{index:03d}"
            clause.sortOrder = index
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
    def _looks_like_heading(text: str) -> bool:
        compact = ContractParserAgent._clean(text).replace(" ", "")
        if not compact or len(compact) > 36:
            return False
        heading_patterns = (
            r"^第[一二三四五六七八九十百零0-9]+[章节条款部分]",
            r"^[一二三四五六七八九十]+、",
            r"^[0-9]+[.、]",
            r"^[（(][0-9一二三四五六七八九十]+[)）]",
        )
        return any(re.match(pattern, compact) for pattern in heading_patterns)

    @staticmethod
    def _infer_heading_level(text: str) -> int:
        compact = ContractParserAgent._clean(text).replace(" ", "")
        if re.match(r"^第[一二三四五六七八九十百零0-9]+[章节]", compact):
            return 1
        if re.match(r"^第[一二三四五六七八九十百零0-9]+[条款]", compact):
            return 1
        if re.match(r"^[一二三四五六七八九十]+、", compact):
            return 1
        if re.match(r"^[0-9]+[.、]", compact):
            return 2
        if re.match(r"^[（(][0-9一二三四五六七八九十]+[)）]", compact):
            return 3
        return 1

    @staticmethod
    def _extract_section_code(text: str) -> str | None:
        compact = ContractParserAgent._clean(text).replace(" ", "")
        patterns = [
            r"^(第[一二三四五六七八九十百零0-9]+[章节条款部分])",
            r"^([一二三四五六七八九十]+、)",
            r"^([0-9]+[.、])",
            r"^([（(][0-9一二三四五六七八九十]+[)）])",
        ]
        for pattern in patterns:
            match = re.match(pattern, compact)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _find_clause_anchor(
        pages: list[ContractPage],
        keywords: list[str],
    ) -> tuple[ContractPage, Any] | None:
        best_match: tuple[int, ContractPage, Any] | None = None
        normalized_keywords = [ContractParserAgent._clean(keyword) for keyword in keywords if ContractParserAgent._clean(keyword)]
        for page in pages:
            for block in page.blocks:
                text = ContractParserAgent._clean(block.text)
                if not text:
                    continue
                score = sum(1 for keyword in normalized_keywords if keyword in text)
                if score <= 0:
                    continue
                weighted = score * 20 + min(len(text), 200) // 20
                if best_match is None or weighted > best_match[0]:
                    best_match = (weighted, page, block)
        if best_match is None:
            return None
        return best_match[1], best_match[2]

    @staticmethod
    def _extract_cross_references(text: str) -> list[str]:
        matches = re.findall(r"(第[一二三四五六七八九十百零0-9]+条|附件[一二三四五六七八九十0-9]+)", ContractParserAgent._clean(text))
        seen: set[str] = set()
        ordered: list[str] = []
        for item in matches:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered[:8]

    @staticmethod
    def _normalize_reference_list(value: Any) -> list[str]:
        if isinstance(value, list):
            items = [ContractParserAgent._clean(item) for item in value]
        elif isinstance(value, str):
            items = re.split(r"[，,；;、\n]+", value)
        else:
            items = []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = ContractParserAgent._clean(item)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized[:8]

    @staticmethod
    def _normalize_structured_fields(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                ContractParserAgent._clean(key): ContractParserAgent._compact_summary(str(val), 80)
                for key, val in value.items()
                if ContractParserAgent._clean(key) and ContractParserAgent._clean(val)
            }
        return {}

    @staticmethod
    def _nearest_section_title(page_number: int, sections: list[ContractSection]) -> str | None:
        candidates = [section for section in sections if section.page <= page_number]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item.page, item.sortOrder))
        return candidates[-1].title

    @staticmethod
    def _pick_first_array(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    async def _safe_list_call(coroutine: Any) -> list[Any]:
        try:
            return await coroutine
        except Exception:
            return []

    async def _gather_limited(self, coroutines: list[Any], limit: int) -> list[Any]:
        semaphore = asyncio.Semaphore(max(1, limit))

        async def runner(coro: Any) -> Any:
            async with semaphore:
                return await coro

        return await asyncio.gather(*(runner(coro) for coro in coroutines))

    @staticmethod
    def _chunk_items(items: list[Any], size: int) -> list[list[Any]]:
        return [items[index : index + size] for index in range(0, len(items), max(1, size))]

    @staticmethod
    async def _empty_batches() -> list[list[dict[str, Any]]]:
        return []
