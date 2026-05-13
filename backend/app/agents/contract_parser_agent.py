from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.contract import ClauseTag, ContractPage, ContractSection, KeyFact
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


class ContractParserAgent:
    def __init__(self, qwen_service: QwenService) -> None:
        self.qwen_service = qwen_service

    async def reconstruct_sections(self, pages: list[ContractPage]) -> list[ContractSection]:
        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "你是合同审阅专家。请根据合同文本块识别合同章节结构。"
                "返回章节树，不要编造不存在的章节；如果章节不明确，请降低置信度。"
            ),
            user_prompt=(
                "请基于以下合同页面内容，输出 sections 数组。"
                "每个元素必须包含 title、level、page、summary、confidence。\n"
                f"{self._pages_payload(pages)}"
            ),
            schema={"type": "object"},
        )

        raw_sections = self._pick_first_array(payload, ["sections", "chapter_tree", "章节", "chapterTree"])
        sections: list[ContractSection] = []
        for index, item in enumerate(raw_sections, start=1):
            title = self._clean(item.get("title") or item.get("标题") or "")
            if not title:
                continue
            page = int(item.get("page") or self._locate_page_by_text(pages, title))
            sections.append(
                ContractSection(
                    id=f"section_{index:03d}",
                    title=title,
                    level=max(1, int(item.get("level", 1))),
                    page=max(1, page),
                    summary=self._clean(item.get("summary") or item.get("摘要") or title),
                    confidence=self._clamp_confidence(item.get("confidence", item.get("置信度", 0.82))),
                )
            )
        return sections

    async def identify_clauses(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
    ) -> list[ClauseTag]:
        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "你是审计风控场景下的合同条款识别专家。"
                "请识别合同中的关键条款，并从给定标签集中选择最合适的标签。"
            ),
            user_prompt=(
                f"可选标签：{CLAUSE_LABELS}\n"
                f"合同章节：{json.dumps([item.model_dump() for item in sections], ensure_ascii=False)}\n"
                f"合同页面内容：{self._pages_payload(pages)}\n"
                "请输出 clauses 数组。每个条款必须包含 label、title、summary、rawText、page、confidence、needHumanReview。"
            ),
            schema={"type": "object"},
        )

        raw_clauses = self._pick_first_array(payload, ["clauses", "clause_tags", "条款", "clauseTags"])
        clauses: list[ClauseTag] = []
        for index, item in enumerate(raw_clauses, start=1):
            label = self._normalize_label(item.get("label") or item.get("tag") or item.get("标签") or "其他重要条款")
            raw_text = self._clean(
                item.get("rawText")
                or item.get("raw_text")
                or item.get("evidence_text")
                or item.get("原文")
                or item.get("摘录")
                or ""
            )
            title = self._clean(item.get("title") or item.get("标题") or label)
            page = int(item.get("page") or self._locate_page_by_text(pages, raw_text or title))
            clauses.append(
                ClauseTag(
                    id=f"clause_{index:03d}",
                    label=label,
                    title=title,
                    summary=self._clean(item.get("summary") or item.get("摘要") or raw_text[:120] or title),
                    rawText=raw_text,
                    page=max(1, page),
                    confidence=self._clamp_confidence(item.get("confidence", item.get("置信度", 0.8))),
                    evidenceId="",
                    needHumanReview=self._to_bool(
                        item.get("needHumanReview", item.get("need_human_review", item.get("建议复核", False)))
                    ),
                    relatedAuditFocusIds=[],
                )
            )
        return clauses

    async def extract_key_facts(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
    ) -> list[KeyFact]:
        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "你是合同关键信息抽取专家。请抽取合同关键字段，"
                "只返回能在原文中找到依据的信息。"
            ),
            user_prompt=(
                f"合同页面内容：{self._pages_payload(pages)}\n"
                f"已识别条款：{json.dumps([item.model_dump(exclude={'evidenceId', 'relatedAuditFocusIds'}) for item in clauses], ensure_ascii=False)}\n"
                "请输出 keyFacts 数组，优先抽取合同名称、甲方、乙方、项目名称、合同金额、付款安排、履约期限、验收标准、争议解决、账户信息。"
                "每个元素包含 label、value、page、confidence、notes。"
            ),
            schema={"type": "object"},
        )

        raw_facts = self._pick_first_array(payload, ["keyFacts", "facts", "关键信息", "字段"])
        key_facts: list[KeyFact] = []
        for index, item in enumerate(raw_facts, start=1):
            label = self._clean(item.get("label") or item.get("name") or item.get("字段") or f"字段{index}")
            value = self._clean(item.get("value") or item.get("content") or item.get("内容") or item.get("值") or "")
            if not label or not value:
                continue
            page = int(item.get("page") or self._locate_page_by_text(pages, value or label))
            key_facts.append(
                KeyFact(
                    id=f"fact_{index:03d}",
                    label=label,
                    value=value,
                    page=max(1, page),
                    confidence=self._clamp_confidence(item.get("confidence", item.get("置信度", 0.78))),
                    notes=self._clean(item.get("notes", item.get("备注", ""))) or None,
                )
            )

        if not key_facts:
            key_facts = self._derive_key_facts_from_clauses(clauses)
        return key_facts

    @staticmethod
    def _pages_payload(pages: list[ContractPage]) -> str:
        compact_pages: list[dict[str, Any]] = []
        for page in pages:
            page_text = "\n".join(block.text for block in page.blocks[:80] if block.text.strip())
            compact_pages.append(
                {
                    "page": page.page,
                    "title": page.title,
                    "text": page_text[:5000],
                }
            )
        return json.dumps(compact_pages, ensure_ascii=False)

    @staticmethod
    def _pick_first_array(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _normalize_label(label: str) -> str:
        label = ContractParserAgent._clean(label)
        return label if label in CLAUSE_LABELS else "其他重要条款"

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.5
        return max(0.01, min(score, 0.99))

    @staticmethod
    def _clean(value: Any) -> str:
        text = str(value or "").strip()
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "是", "建议复核"}
        return bool(value)

    @staticmethod
    def _locate_page_by_text(pages: list[ContractPage], target_text: str) -> int:
        normalized_target = ContractParserAgent._clean(target_text).replace(" ", "")
        if not normalized_target:
            return 1
        anchor = normalized_target[:18]
        for page in pages:
            page_text = "".join(block.text for block in page.blocks).replace(" ", "")
            if anchor and anchor in page_text:
                return page.page
        return 1

    @staticmethod
    def _derive_key_facts_from_clauses(clauses: list[ClauseTag]) -> list[KeyFact]:
        key_facts: list[KeyFact] = []
        for clause in clauses:
            if clause.label == "甲乙方信息":
                party_a = re.search(r"甲方[:：]\s*([^\n；，。]+)", clause.rawText)
                party_b = re.search(r"乙方[:：]\s*([^\n；，。]+)", clause.rawText)
                if party_a:
                    key_facts.append(
                        KeyFact(
                            id="fact_001",
                            label="甲方",
                            value=party_a.group(1).strip(),
                            page=clause.page,
                            confidence=min(0.95, clause.confidence),
                        )
                    )
                if party_b:
                    key_facts.append(
                        KeyFact(
                            id="fact_002",
                            label="乙方",
                            value=party_b.group(1).strip(),
                            page=clause.page,
                            confidence=min(0.95, clause.confidence),
                        )
                    )

            if clause.label == "合同金额":
                amount = re.search(r"(人民币\s*[\d,]+(?:\.\d+)?\s*元)", clause.rawText)
                if amount:
                    key_facts.append(
                        KeyFact(
                            id="fact_003",
                            label="合同金额",
                            value=amount.group(1).strip(),
                            page=clause.page,
                            confidence=min(0.94, clause.confidence),
                        )
                    )

            if clause.label == "付款条件":
                key_facts.append(
                    KeyFact(
                        id="fact_004",
                        label="付款安排",
                        value=clause.rawText[:180],
                        page=clause.page,
                        confidence=min(0.9, clause.confidence),
                    )
                )

            if clause.label == "验收标准":
                key_facts.append(
                    KeyFact(
                        id="fact_005",
                        label="验收标准",
                        value=clause.rawText[:180],
                        page=clause.page,
                        confidence=min(0.9, clause.confidence),
                    )
                )

            if clause.label == "争议解决":
                key_facts.append(
                    KeyFact(
                        id="fact_006",
                        label="争议解决",
                        value=clause.rawText[:180],
                        page=clause.page,
                        confidence=min(0.9, clause.confidence),
                    )
                )

        dedup: dict[tuple[str, str], KeyFact] = {}
        for item in key_facts:
            dedup[(item.label, item.value)] = item
        return list(dedup.values())
