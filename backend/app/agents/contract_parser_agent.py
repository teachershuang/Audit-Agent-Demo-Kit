from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, TypeVar

from app.config import Settings
from app.prompts.context import build_relation_prompt_context
from app.prompts.contract import (
    build_clause_semantic_prompt,
    build_key_fact_prompt,
    build_overview_text_prompt,
    build_overview_vl_prompt,
    build_section_semantic_prompt,
)
from app.schemas.contract import ClauseTag, ContractPage, ContractSection, KeyFact
from app.schemas.relation import RelationConfig
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

T = TypeVar("T")


class ContractParserAgent:
    def __init__(self, qwen_service: QwenService, settings: Settings) -> None:
        self.qwen_service = qwen_service
        self.settings = settings
        self.parallelism = max(1, settings.qwen_parallel_requests)
        self.key_fact_batch_size = max(2, settings.key_fact_batch_size)

    def derive_section_hints(self, pages: list[ContractPage]) -> list[ContractSection]:
        hints: list[ContractSection] = []
        seen: set[tuple[int, str]] = set()
        for page in pages:
            for block in page.blocks[:16]:
                title = self._clean(block.text)
                if not title or not self._looks_like_heading(title):
                    continue
                key = (page.page, title)
                if key in seen:
                    continue
                seen.add(key)
                hints.append(
                    ContractSection(
                        id=f"hint_{len(hints) + 1:03d}",
                        title=title[:40],
                        level=self._infer_heading_level(title),
                        page=page.page,
                        summary=title[:120],
                        confidence=0.58,
                        blockIds=[block.id],
                        evidenceId=None,
                    )
                )
                if len(hints) >= 24:
                    return hints
        return hints

    async def reconstruct_sections(self, pages: list[ContractPage]) -> list[ContractSection]:
        semantic_sections = await self._request_sections(pages)
        semantic_results = self._build_sections_from_items(semantic_sections, pages)
        if self._derived_sections_are_sufficient(semantic_results, pages):
            return semantic_results
        return self._derive_sections_locally(pages)

    async def identify_clauses(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
        relations: list[RelationConfig] | None = None,
    ) -> list[ClauseTag]:
        semantic_clauses = await self._request_clauses(pages, sections, relations or [])
        semantic_results = self._build_clauses_from_items(semantic_clauses, pages)
        if self._derived_clauses_are_sufficient(semantic_results):
            return self._dedupe_clauses(semantic_results)
        return self._dedupe_clauses(self._derive_clauses_locally(pages))

    async def extract_key_facts(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
    ) -> list[KeyFact]:
        derived_facts = self._dedupe_key_facts(
            self._derive_key_facts_from_pages(pages) + self._derive_key_facts_from_clauses(clauses)
        )

        overview_task = self._request_overview_key_facts(pages, clauses)
        clause_batches = self._chunk_items(clauses, self.key_fact_batch_size)
        batch_tasks = [self._request_key_facts(batch) for batch in clause_batches]

        overview_result, raw_batches = await asyncio.gather(
            self._safe_list_call(overview_task),
            self._gather_limited(batch_tasks, min(self.parallelism, max(1, len(batch_tasks))))
            if batch_tasks
            else self._empty_batches(),
        )

        facts: list[KeyFact] = []
        for batch in raw_batches:
            for index, item in enumerate(batch, start=len(facts) + 1):
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

        merged = self._dedupe_key_facts(overview_result + derived_facts + facts)
        self._ensure_required_overview_facts(merged)
        return self._dedupe_key_facts(merged)

    async def _request_overview_key_facts(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
    ) -> list[KeyFact]:
        clause_payload = [
            {
                "id": clause.id,
                "label": clause.label,
                "coreLabel": clause.coreLabel,
                "summary": clause.summary[:220],
                "rawText": clause.rawText[:600],
                "page": clause.page,
            }
            for clause in clauses[:18]
        ]
        page_payload = [
            {
                "page": page.page,
                "text": "\n".join(self._clean(block.text) for block in page.blocks[:32])[:2200],
            }
            for page in pages[:4]
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

        items = self._pick_first_array(payload, ["overviewFacts", "keyFacts", "facts"])
        facts: list[KeyFact] = []
        allowed_labels = {"合同编号", "主体摘要", "甲乙方信息", "服务内容"}
        for index, item in enumerate(items, start=1):
            label = self._normalize_overview_label(self._clean(item.get("label") or item.get("name")))
            if label not in allowed_labels:
                continue
            value = self._clean(item.get("value") or item.get("content"))
            if not value:
                continue
            evidence_text = self._clean(item.get("evidenceText") or item.get("evidence") or value)
            page = self._coerce_page(item.get("page"), pages, evidence_text or value)
            facts.append(
                KeyFact(
                    id=f"overview_{index:03d}",
                    label=label,
                    value=value,
                    page=page,
                    confidence=self._clamp_confidence(item.get("confidence")),
                    evidenceId=self._clean(item.get("evidenceId")) or self._locate_evidence_id(pages, page, evidence_text),
                    notes=self._clean(item.get("notes") or item.get("remark")) or None,
                )
            )
        return facts

    async def _request_sections(self, pages: list[ContractPage]) -> list[dict[str, Any]]:
        prompt = build_section_semantic_prompt(self._pages_payload(pages))
        payload = await self.qwen_service.chat_json(
            system_prompt=prompt.system,
            user_prompt=prompt.user,
            schema={"type": "object"},
            timeout=120,
        )
        return self._pick_first_array(payload, ["sections", "chapterTree", "chapter_tree", "章节", "章节树"])

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
                "summary": section.summary,
            }
            for section in sections[:48]
        ]
        prompt = build_clause_semantic_prompt(
            self._pages_payload(pages),
            section_payload,
            CLAUSE_LABELS,
            build_relation_prompt_context(relations),
        )
        payload = await self.qwen_service.chat_json(
            system_prompt=prompt.system,
            user_prompt=prompt.user,
            schema={"type": "object"},
            timeout=150,
        )
        raw = self._pick_first_array(payload, ["clauses", "clauseTags", "clause_tags", "条款", "条款标签"])
        return raw or self._clauses_from_structured_payload(payload)

    async def _request_key_facts(self, clauses: list[ClauseTag]) -> list[dict[str, Any]]:
        clause_payload = [
            {
                "id": clause.id,
                "label": clause.label,
                "coreLabel": clause.coreLabel,
                "title": clause.title,
                "summary": clause.summary,
                "rawText": clause.rawText[:500],
                "page": clause.page,
                "confidence": clause.confidence,
            }
            for clause in clauses[:36]
        ]
        prompt = build_key_fact_prompt(clause_payload)
        payload = await self.qwen_service.chat_json(
            system_prompt=prompt.system,
            user_prompt=prompt.user,
            schema={"type": "object"},
            timeout=90,
        )
        return self._pick_first_array(payload, ["keyFacts", "facts", "key_facts", "关键信息"])

    def _build_sections_from_items(
        self,
        items: list[dict[str, Any]],
        pages: list[ContractPage],
    ) -> list[ContractSection]:
        sections: list[ContractSection] = []
        seen: set[tuple[int, str]] = set()
        for item in items:
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
                    id=self._clean(item.get("id")) or f"section_{len(sections) + 1:03d}",
                    title=title,
                    level=self._coerce_level(item.get("level")),
                    page=page,
                    summary=self._clean(item.get("summary")) or evidence_text[:120],
                    confidence=self._clamp_confidence(item.get("confidence")),
                    blockIds=[],
                    evidenceId=None,
                )
            )
        sections.sort(key=lambda section: (section.page, section.level, section.title))
        for index, section in enumerate(sections, start=1):
            section.id = f"section_{index:03d}"
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
            label_source = self._normalize_label_source(
                item.get("labelSource") or item.get("label_source"),
                label=label,
                core_label=core_label,
            )
            raw_text = self._clean(item.get("rawText") or item.get("text") or item.get("quote"))
            summary = self._clean(item.get("summary")) or self._summarize_clause_text(raw_text)
            page = self._coerce_page(item.get("page"), pages, raw_text or summary)
            clauses.append(
                ClauseTag(
                    id=self._clean(item.get("id")) or f"clause_{index:03d}",
                    label=label,
                    coreLabel=core_label,
                    labelSource=label_source,
                    title=self._clean(item.get("title")) or label,
                    summary=summary[:220],
                    rawText=raw_text or summary,
                    page=page,
                    confidence=self._clamp_confidence(item.get("confidence")),
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
                        summary=self._build_section_summary(title, title),
                        confidence=0.58,
                        blockIds=[],
                        evidenceId=None,
                    )
                )
        if not sections and pages:
            sections.append(
                ContractSection(
                    id="section_001",
                    title="合同正文",
                    level=1,
                    page=pages[0].page,
                    summary="未稳定识别出显式章节标题，建议人工复核。",
                    confidence=0.35,
                    blockIds=[],
                    evidenceId=None,
                )
            )
        return sections

    def _derive_clauses_locally(self, pages: list[ContractPage]) -> list[ClauseTag]:
        keyword_map = {
            "甲乙方信息": ["甲方", "乙方", "委托方", "受托方"],
            "合同金额": ["合同金额", "总额", "万元", "人民币"],
            "付款条件": ["付款", "支付", "比例", "节点"],
            "履约期限": ["期限", "工期", "完成时间", "服务期"],
            "服务/采购/工程内容": ["服务内容", "工作内容", "技术服务", "采购内容"],
            "验收标准": ["验收", "交付", "成果", "标准"],
            "违约责任": ["违约", "赔偿", "责任", "逾期"],
            "权利义务": ["权利", "义务", "双方约定"],
            "保密条款": ["保密", "秘密", "披露"],
            "争议解决": ["争议", "仲裁", "法院", "协商"],
            "账户信息": ["开户", "账号", "账户", "银行"],
            "附件条款": ["附件", "附表", "补充协议"],
        }
        clauses: list[ClauseTag] = []
        for label, keywords in keyword_map.items():
            anchor = self._find_clause_anchor(pages, keywords)
            if anchor is None:
                continue
            page, block = anchor
            clauses.append(
                ClauseTag(
                    id=f"clause_{len(clauses) + 1:03d}",
                    label=label,
                    coreLabel=label if label in CLAUSE_LABELS else "其他重要条款",
                    labelSource="core",
                    title=label,
                    summary=self._summarize_clause_text(block.text),
                    rawText=self._clean(block.text),
                    page=page.page,
                    confidence=0.52,
                    blockIds=[],
                    evidenceId="",
                    needHumanReview=True,
                    discoveryReason="基于关键词和版面位置的本地兜底识别。",
                    relatedAuditFocusIds=[],
                )
            )
        return clauses

    @staticmethod
    def _clauses_from_structured_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        labels = payload.get("labels")
        raw_texts = payload.get("rawTexts") or payload.get("raw_texts")
        summaries = payload.get("summaries")
        if not isinstance(labels, list):
            return results
        for index, label in enumerate(labels):
            if not isinstance(label, str):
                continue
            results.append(
                {
                    "label": label,
                    "summary": summaries[index] if isinstance(summaries, list) and index < len(summaries) else label,
                    "rawText": raw_texts[index] if isinstance(raw_texts, list) and index < len(raw_texts) else label,
                    "page": 1,
                    "confidence": 0.55,
                }
            )
        return results

    @staticmethod
    def _pages_payload(pages: list[ContractPage]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for page in pages:
            blocks = [ContractParserAgent._clean(block.text) for block in page.blocks[:36] if ContractParserAgent._clean(block.text)]
            payload.append(
                {
                    "page": page.page,
                    "title": page.title,
                    "text": "\n".join(blocks)[:4500],
                }
            )
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
            "帐户信息": "账户信息",
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
        if compact in {"合同编号", "协议编号", "编号"}:
            return "合同编号"
        if compact in {"主体摘要", "主体信息摘要", "合同主体摘要", "合同基本信息"}:
            return "主体摘要"
        if compact in {"甲乙方信息", "合同主体信息", "双方主体信息", "主体信息"}:
            return "甲乙方信息"
        if compact in {"服务内容", "项目内容", "服务/采购/工程内容", "合同服务内容"}:
            return "服务内容"
        return compact

    @staticmethod
    def _ensure_required_overview_facts(facts: list[KeyFact]) -> None:
        required = {
            "合同编号": "未提取",
            "主体摘要": "待提取",
            "甲乙方信息": "待提取",
            "服务内容": "待提取",
        }
        labels = {fact.label for fact in facts}
        for label, fallback in required.items():
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
        patterns = [
            re.compile(r"(?:合同|协议|项目)?(?:编号|备案号|合同编号|协议编号)\s*[:：]?\s*([A-Za-z0-9\u4e00-\u9fa5\\-_/().（）]{4,80})"),
            re.compile(r"\b([A-Z]{1,6}-\d{4,}[-A-Z0-9/]*)\b"),
        ]
        for page in pages[: min(len(pages), 4)]:
            for block in page.blocks[:80]:
                text = ContractParserAgent._clean(block.text)
                if not text:
                    continue
                for pattern in patterns:
                    match = pattern.search(text)
                    if not match:
                        continue
                    value = match.group(1).strip().strip("。；;，,")
                    if len(value) < 4:
                        continue
                    dedupe_key = value.lower()
                    if dedupe_key in seen_values:
                        continue
                    seen_values.add(dedupe_key)
                    facts.append(
                        KeyFact(
                            id=f"fact_{len(facts) + 1:03d}",
                            label="合同编号",
                            value=value,
                            page=page.page,
                            confidence=0.9 if "编号" in text else 0.72,
                            evidenceId=block.id,
                            notes="基于 OCR 原文块直接提取。",
                        )
                    )
                    break
        return facts

    @staticmethod
    def _derive_key_facts_from_clauses(clauses: list[ClauseTag]) -> list[KeyFact]:
        facts: list[KeyFact] = []
        seen: set[tuple[str, str, int]] = set()
        party_pattern = re.compile(r"(甲方|乙方|委托方|受托方)\s*[（(]?\s*[:：]?\s*([^\n（）()]{2,80})")
        amount_pattern = re.compile(r"(?:人民币|合同总额|总金额|金额)[^0-9]{0,8}([0-9][0-9,，.]*\s*(?:元|万元)?)")
        contract_number_pattern = re.compile(
            r"(?:合同|协议|项目)?(?:编号|备案号|合同编号|协议编号)\s*[:：]?\s*([A-Za-z0-9\u4e00-\u9fa5\\-_/().（）]{4,80})"
        )

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
            if clause_key == "合同基本信息":
                number_match = contract_number_pattern.search(clause.rawText)
                if number_match:
                    add_fact("合同编号", number_match.group(1), clause)
                add_fact("合同基本信息", clause.summary or clause.rawText[:160], clause)
            elif clause_key == "甲乙方信息":
                matched = False
                for match in party_pattern.finditer(clause.rawText):
                    add_fact(match.group(1), match.group(2), clause)
                    matched = True
                add_fact("甲乙方信息", clause.summary or clause.rawText[:120], clause)
                if not matched:
                    add_fact("主体摘要", clause.summary or clause.rawText[:120], clause, notes="主体名称建议人工复核")
            elif clause_key == "合同金额":
                match = amount_pattern.search(clause.rawText)
                add_fact("合同金额", match.group(1) if match else clause.summary, clause)
            elif clause_key == "付款条件":
                add_fact("付款条件", clause.summary or clause.rawText[:160], clause)
            elif clause_key == "履约期限":
                add_fact("履约期限", clause.summary or clause.rawText[:160], clause)
            elif clause_key == "验收标准":
                add_fact("验收标准", clause.summary or clause.rawText[:160], clause)
            elif clause_key == "争议解决":
                add_fact("争议解决", clause.summary or clause.rawText[:160], clause)
            elif clause_key == "账户信息":
                add_fact("账户信息", clause.summary or clause.rawText[:160], clause)
            elif clause_key == "服务/采购/工程内容":
                add_fact("服务内容", clause.summary or clause.rawText[:160], clause)
        return facts

    @staticmethod
    def _dedupe_clauses(clauses: list[ClauseTag]) -> list[ClauseTag]:
        best_by_key: dict[str, ClauseTag] = {}
        for clause in clauses:
            clause_key = clause.coreLabel if clause.labelSource in {"core", "user_configured"} and clause.coreLabel else clause.label
            current = best_by_key.get(clause_key)
            if current is None:
                best_by_key[clause_key] = clause
                continue
            candidate_score = (clause.confidence, len(clause.rawText))
            current_score = (current.confidence, len(current.rawText))
            if candidate_score > current_score:
                best_by_key[clause_key] = clause
        deduped = list(best_by_key.values())
        deduped.sort(
            key=lambda item: (
                item.page,
                CLAUSE_LABELS.index(item.coreLabel) if item.coreLabel in CLAUSE_LABELS else 99,
                item.label,
            )
        )
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
        if len(sections) < min(4, max(2, len(pages) // 2)):
            return False
        covered_pages = {section.page for section in sections}
        return len(covered_pages) >= min(2, len(pages))

    @staticmethod
    def _derived_clauses_are_sufficient(clauses: list[ClauseTag]) -> bool:
        critical = {
            "甲乙方信息",
            "合同金额",
            "付款条件",
            "服务/采购/工程内容",
            "验收标准",
            "违约责任",
            "争议解决",
        }
        labels = {clause.coreLabel or clause.label for clause in clauses}
        return len(clauses) >= 8 and len(labels & critical) >= 5

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
    def _build_section_summary(block_text: str, title: str) -> str:
        source = ContractParserAgent._clean(block_text)
        if not source:
            return title
        if source.startswith(title):
            source = source[len(title) :].strip(" ：:，,。")
        return source[:120] or title

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
    def _summarize_clause_text(raw_text: str) -> str:
        cleaned = ContractParserAgent._clean(raw_text)
        return cleaned.replace("\n", " ")[:160]

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

    @staticmethod
    async def _empty_batches() -> list[list[dict[str, Any]]]:
        return []

    @staticmethod
    def _chunk_items(items: list[T], batch_size: int) -> list[list[T]]:
        if not items:
            return []
        return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]

    async def _gather_limited(self, coroutines: list[Any], limit: int) -> list[Any]:
        semaphore = asyncio.Semaphore(max(1, limit))

        async def run(coroutine: Any) -> Any:
            async with semaphore:
                return await coroutine

        return list(await asyncio.gather(*(run(coroutine) for coroutine in coroutines)))
