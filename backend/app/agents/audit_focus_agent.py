from __future__ import annotations

import asyncio
import json
from typing import Any

from app.schemas.audit import AuditFocus
from app.schemas.contract import ClauseTag, ContractSection, KeyFact
from app.schemas.relation import RelationConfig
from app.services.qwen_service import QwenService


class AuditFocusAgent:
    def __init__(self, qwen_service: QwenService) -> None:
        self.qwen_service = qwen_service

    async def generate(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        key_facts: list[KeyFact],
    ) -> list[AuditFocus]:
        clause_map = {clause.id: clause for clause in clauses}
        if not clauses:
            return []

        groups = self._build_groups(clauses=clauses, relations=relations, key_facts=key_facts)
        payloads = await asyncio.gather(
            *[
                self._request_focus_batch(
                    sections=sections,
                    clauses=group["clauses"],
                    relations=group["relations"],
                    key_facts=group["key_facts"],
                    focus_hint=group["focus_hint"],
                )
                for group in groups
                if group["clauses"]
            ]
        )

        raw_items: list[dict[str, Any]] = []
        for payload in payloads:
            raw_items.extend(self._pick_first_array(payload, ["auditFocuses", "关注事项", "audit_focuses"]))

        model_focuses = self._build_focuses_from_items(raw_items, clauses, relations, clause_map)
        if model_focuses:
            return self._dedupe_audit_focuses(model_focuses + self._derive_relation_fallbacks(clauses, relations))

        return self._dedupe_audit_focuses(self._derive_relation_fallbacks(clauses, relations))

    async def _request_focus_batch(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        key_facts: list[KeyFact],
        focus_hint: str,
    ) -> dict[str, Any]:
        clause_payload = [
            {
                "id": clause.id,
                "label": clause.label,
                "coreLabel": clause.coreLabel,
                "labelSource": clause.labelSource,
                "summary": clause.summary,
                "page": clause.page,
                "confidence": clause.confidence,
            }
            for clause in clauses
        ]
        relation_payload = [
            {
                "id": relation.id,
                "name": relation.name,
                "description": relation.description,
                "enabled": relation.enabled,
                "riskPrompt": relation.riskPrompt,
                "toolSource": [tool.value for tool in relation.toolSource],
                "priority": relation.priority.value,
            }
            for relation in relations
            if relation.enabled
        ]
        fact_payload = [fact.model_dump() for fact in key_facts[:30]]
        section_payload = [
            {
                "id": section.id,
                "title": section.title,
                "page": section.page,
                "summary": section.summary,
            }
            for section in sections[:30]
        ]
        return await self.qwen_service.chat_json(
            system_prompt=(
                "你是审计风控辅助分析 Agent。"
                "请基于合同章节、条款、关键信息和用户配置的关系关注项，生成审计关注方向。"
                "不能输出最终审计结论，只能输出关注方向、疑似风险或待核验事项。"
                "既要响应用户配置的关系关注项，也可以主动发现新的关注方向。"
                "对于内部关联交易、供应商关系、账户异常等，必须使用“疑似”“待核验”“建议接入外部数据确认”的措辞。"
                "所有输出必须是中文。"
            ),
            user_prompt=(
                f"关注主题：{focus_hint}\n"
                f"章节：\n{json.dumps(section_payload, ensure_ascii=False)}\n"
                f"条款：\n{json.dumps(clause_payload, ensure_ascii=False)}\n"
                f"关键信息：\n{json.dumps(fact_payload, ensure_ascii=False)}\n"
                f"关系配置：\n{json.dumps(relation_payload, ensure_ascii=False)}\n"
                "请返回 JSON 对象，顶层字段为 `auditFocuses`。"
                "每个关注项包含：title, focusSource, matchedRelationIds, riskLevel, reason, evidenceClauseIds, locationText, confidence, dependsOn, currentBasis, futureTools, modelOnly, humanReviewSuggestion。"
                "focusSource 只能是 `relation_config`、`agent_discovered`、`hybrid` 之一。"
                "matchedRelationIds 只能引用输入中的关系配置 id。"
            ),
            schema={"type": "object"},
            timeout=120,
        )

    @staticmethod
    def _build_groups(
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        key_facts: list[KeyFact],
    ) -> list[dict[str, Any]]:
        relation_sensitive = {"甲乙方信息", "账户信息", "合同金额", "付款条件", "其他重要条款"}
        performance_sensitive = {"付款条件", "验收标准", "违约责任", "权利义务", "履约期限", "附件条款"}
        groups = [
            {
                "focus_hint": "履约、付款、验收、违约、交付闭环",
                "clauses": [clause for clause in clauses if clause.coreLabel in performance_sensitive] or clauses[:8],
                "relations": [],
                "key_facts": [fact for fact in key_facts if fact.label in {"付款条件", "验收标准", "履约期限", "合同金额"}],
            },
            {
                "focus_hint": "主体、账户、供应商关系、疑似关联、外部核验依赖",
                "clauses": [clause for clause in clauses if clause.coreLabel in relation_sensitive] or clauses[-8:],
                "relations": [relation for relation in relations if relation.enabled],
                "key_facts": [fact for fact in key_facts if fact.label in {"甲方", "乙方", "甲乙方信息", "账户信息", "合同金额"}],
            },
        ]
        return groups

    def _build_focuses_from_items(
        self,
        items: list[dict[str, Any]],
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        clause_map: dict[str, ClauseTag],
    ) -> list[AuditFocus]:
        valid_clause_ids = {clause.id for clause in clauses}
        valid_relation_ids = {relation.id for relation in relations}
        focuses: list[AuditFocus] = []
        for index, item in enumerate(items, start=1):
            clause_ids = [
                clause_id
                for clause_id in self._to_list(item.get("evidenceClauseIds") or item.get("evidence_clause_ids"))
                if clause_id in valid_clause_ids
            ]
            if not clause_ids:
                continue
            matched_relation_ids = [
                relation_id
                for relation_id in self._to_list(item.get("matchedRelationIds") or item.get("matched_relation_ids"))
                if relation_id in valid_relation_ids
            ]
            title = self._clean(item.get("title") or item.get("name"))
            reason = self._clean(item.get("reason"))
            if not title or not reason:
                continue
            focus_source = self._normalize_focus_source(item.get("focusSource"), matched_relation_ids)
            location_text = self._clean(item.get("locationText") or item.get("location"))
            if not location_text:
                location_text = self._build_location_text(clause_ids, clause_map)
            focuses.append(
                AuditFocus(
                    id=self._clean(item.get("id")) or f"audit_{index:03d}",
                    title=title,
                    focusSource=focus_source,
                    matchedRelationIds=matched_relation_ids,
                    riskLevel=self._normalize_risk_level(item.get("riskLevel")),
                    reason=reason,
                    evidenceClauseIds=clause_ids,
                    locationText=location_text,
                    confidence=self._clamp_confidence(item.get("confidence")),
                    dependsOn=self._to_list(item.get("dependsOn") or item.get("depends_on")),
                    currentBasis=self._clean(item.get("currentBasis") or item.get("current_basis"))
                    or "当前基于合同文本、OCR 结果和 Agent 推理生成，仍需结合外部数据或业务单据核验。",
                    futureTools=self._normalize_future_tools(self._to_list(item.get("futureTools") or item.get("future_tools"))),
                    modelOnly=self._to_bool(item.get("modelOnly")) if item.get("modelOnly") is not None else True,
                    humanReviewSuggestion=self._clean(
                        item.get("humanReviewSuggestion") or item.get("human_review_suggestion")
                    )
                    or "建议审计人员结合合同原文、业务单据和外部系统进一步复核。",
                )
            )
        return focuses

    def _derive_relation_fallbacks(
        self,
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
    ) -> list[AuditFocus]:
        clause_by_core = {clause.coreLabel: clause for clause in clauses}
        focuses: list[AuditFocus] = []
        for relation in relations:
            if not relation.enabled:
                continue
            related_clause_ids: list[str] = []
            depends_on: list[str] = []
            if "账户" in relation.name and clause_by_core.get("账户信息"):
                related_clause_ids.append(clause_by_core["账户信息"].id)
                depends_on.append("账户信息")
            if "供应商" in relation.name and clause_by_core.get("甲乙方信息"):
                related_clause_ids.append(clause_by_core["甲乙方信息"].id)
                depends_on.append("甲乙方信息")
            if "付款" in relation.name and clause_by_core.get("付款条件"):
                related_clause_ids.append(clause_by_core["付款条件"].id)
                depends_on.append("付款条件")
            if "项目" in relation.name and clause_by_core.get("服务/采购/工程内容"):
                related_clause_ids.append(clause_by_core["服务/采购/工程内容"].id)
                depends_on.append("服务/采购/工程内容")
            if not related_clause_ids:
                continue
            focuses.append(
                AuditFocus(
                    id=f"audit_relation_{len(focuses) + 1:03d}",
                    title=f"{relation.name}核验",
                    focusSource="relation_config",
                    matchedRelationIds=[relation.id],
                    riskLevel=self._normalize_risk_level("pending_verification"),
                    reason=f"该关注项来自用户配置的关系关注：{relation.description or relation.riskPrompt}",
                    evidenceClauseIds=self._unique_preserve_order(related_clause_ids),
                    locationText=" / ".join(f"第 {clause_by_core[label].page} 页" for label in depends_on if label in clause_by_core),
                    confidence=0.68,
                    dependsOn=depends_on,
                    currentBasis="当前基于合同文本和用户配置关系项生成，建议结合外部数据进一步核验。",
                    futureTools=self._normalize_future_tools([tool.value for tool in relation.toolSource]),
                    modelOnly=False,
                    humanReviewSuggestion="建议结合企业关系库、主数据或业务系统进一步核验。",
                )
            )
        return focuses

    @staticmethod
    def _pick_first_array(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _build_location_text(clause_ids: list[str], clause_map: dict[str, ClauseTag]) -> str:
        pages = sorted({clause_map[clause_id].page for clause_id in clause_ids if clause_id in clause_map})
        return " / ".join(f"第 {page} 页" for page in pages)

    @staticmethod
    def _normalize_focus_source(value: Any, matched_relation_ids: list[str]) -> str:
        text = str(value or "").strip().lower()
        if text == "relation_config":
            return "relation_config"
        if text == "hybrid":
            return "hybrid"
        if text == "agent_discovered":
            return "agent_discovered"
        return "hybrid" if matched_relation_ids else "agent_discovered"

    @staticmethod
    def _normalize_risk_level(value: Any):
        text = str(value or "").strip().lower()
        if text in {"low", "medium", "high", "pending_verification"}:
            return text
        if text in {"待核验", "pending", "external_pending"}:
            return "pending_verification"
        if text in {"高", "high_risk"}:
            return "high"
        if text in {"低"}:
            return "low"
        return "medium"

    @staticmethod
    def _normalize_future_tools(tools: list[str]) -> list[str]:
        normalized = [tool.strip() for tool in tools if str(tool).strip()]
        if normalized:
            return AuditFocusAgent._unique_preserve_order(normalized)
        return ["知识图谱", "企业工商数据", "内部主数据"]

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.72
        return max(0.01, min(score, 0.99))

    @staticmethod
    def _to_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y", "是"}
        return bool(value)

    @staticmethod
    def _clean(value: Any) -> str:
        return "\n".join(line.strip() for line in str(value or "").replace("\r", "\n").splitlines() if line.strip())

    @staticmethod
    def _unique_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    @staticmethod
    def _dedupe_audit_focuses(items: list[AuditFocus]) -> list[AuditFocus]:
        best_by_key: dict[tuple[str, tuple[str, ...]], AuditFocus] = {}
        for item in items:
            key = (item.title, tuple(sorted(item.evidenceClauseIds)))
            current = best_by_key.get(key)
            if current is None or (item.confidence, len(item.matchedRelationIds)) > (
                current.confidence,
                len(current.matchedRelationIds),
            ):
                best_by_key[key] = item
        deduped = list(best_by_key.values())
        deduped.sort(key=lambda item: (-item.confidence, item.title))
        for index, item in enumerate(deduped, start=1):
            item.id = f"audit_{index:03d}"
        return deduped
