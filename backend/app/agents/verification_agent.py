from __future__ import annotations

from typing import Any

from app.prompts.verification import build_verification_narrative_prompt
from app.schemas.audit import AuditFocus, VerificationItem, VerificationStatus
from app.schemas.contract import ClauseTag, ContractSection
from app.services.qwen_service import QwenService

KEYWORD_RULES = {
    "付款条件": ["付款", "支付", "金额", "比例", "节点"],
    "验收标准": ["验收", "交付", "确认", "标准"],
    "违约责任": ["违约", "赔偿", "逾期", "责任"],
    "争议解决": ["争议", "仲裁", "法院", "协商"],
}


class VerificationAgent:
    def __init__(self, qwen_service: QwenService) -> None:
        self.qwen_service = qwen_service

    async def verify(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        audit_focuses: list[AuditFocus],
        rule_results: dict[str, Any] | None = None,
    ) -> list[VerificationItem]:
        items = self._build_rule_items(
            sections=sections,
            clauses=clauses,
            audit_focuses=audit_focuses,
            rule_results=rule_results or {},
        )
        if not items or not self.qwen_service.is_available:
            return items
        try:
            narratives = await self._request_verification_narratives(items=items, clauses=clauses, audit_focuses=audit_focuses)
        except Exception:
            return items
        return self._merge_narratives(items, narratives)

    def _build_rule_items(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        audit_focuses: list[AuditFocus],
        rule_results: dict[str, Any],
    ) -> list[VerificationItem]:
        items: list[VerificationItem] = []
        clause_by_label = {item.coreLabel or item.label: item for item in clauses}

        required_labels = ["付款条件", "验收标准", "违约责任", "争议解决"]
        for index, label in enumerate(required_labels, start=1):
            clause = clause_by_label.get(label)
            if clause:
                items.append(
                    VerificationItem(
                        id=f"verify_required_{index:03d}",
                        name=f"{label}完整性校验",
                        method="条款识别 / 原文证据定位",
                        status=VerificationStatus.PASS,
                        description=f"已识别到 {label}，并建立了原文证据映射。",
                        relatedClauseIds=[clause.id],
                        relatedEvidenceIds=[clause.evidenceId] if clause.evidenceId else [],
                    )
                )
            else:
                items.append(
                    VerificationItem(
                        id=f"verify_required_{index:03d}",
                        name=f"{label}完整性校验",
                        method="条款识别 / 原文证据定位",
                        status=VerificationStatus.FAIL,
                        description=f"未识别到 {label}。建议回看合同原文并人工复核是否缺失。",
                    )
                )

        for clause in clauses:
            clause_key = clause.coreLabel or clause.label
            keywords = KEYWORD_RULES.get(clause_key)
            if not keywords:
                continue
            hits = [keyword for keyword in keywords if keyword in clause.rawText]
            status = VerificationStatus.PASS if len(hits) >= 2 else VerificationStatus.WARNING
            items.append(
                VerificationItem(
                    id=f"verify_keyword_{clause.id}",
                    name=f"{clause.label}关键词一致性校验",
                    method="关键词命中 / 语义对照",
                    status=status,
                    description=f"命中关键词：{('、'.join(hits)) if hits else '未命中核心关键词'}。",
                    relatedClauseIds=[clause.id],
                    relatedEvidenceIds=[clause.evidenceId] if clause.evidenceId else [],
                )
            )

        low_confidence = [clause for clause in clauses if clause.confidence < 0.65]
        if low_confidence:
            items.append(
                VerificationItem(
                    id="verify_low_confidence",
                    name="低置信度项目复核提示",
                    method="置信度阈值检查",
                    status=VerificationStatus.WARNING,
                    description=f"发现 {len(low_confidence)} 条低置信度条款，建议重点复核。",
                    relatedClauseIds=[clause.id for clause in low_confidence],
                    relatedEvidenceIds=[clause.evidenceId for clause in low_confidence if clause.evidenceId],
                )
            )

        external_audits = [item for item in audit_focuses if item.riskLevel == "pending_verification"]
        if external_audits:
            items.append(
                VerificationItem(
                    id="verify_external_dependencies",
                    name="外部数据依赖检查",
                    method="关注事项依赖分析",
                    status=VerificationStatus.EXTERNAL_PENDING,
                    description=f"发现 {len(external_audits)} 项关注事项需要结合外部数据进一步核验。",
                    relatedClauseIds=sorted({clause_id for item in external_audits for clause_id in item.evidenceClauseIds}),
                    needExternalTool=True,
                    source="external_dependency",
                )
            )

        if sections:
            items.append(
                VerificationItem(
                    id="verify_structure",
                    name="章节结构校验",
                    method="章节识别 / 页码映射",
                    status=VerificationStatus.PASS,
                    description=f"共识别 {len(sections)} 个章节，并完成了顺序和页码映射。",
                )
            )

        items.extend(self._build_engine_summary_items(rule_results))
        items.extend(self._build_engine_rule_items(clauses=clauses, rule_results=rule_results))
        return items

    @staticmethod
    def _build_engine_summary_items(rule_results: dict[str, Any]) -> list[VerificationItem]:
        status = str(rule_results.get("status") or "")
        configured_rules = rule_results.get("configuredRules") or []
        matched_rules = rule_results.get("matchedRules") or []
        missing_rules = rule_results.get("missingConfiguredRules") or []
        unmatched_rules = rule_results.get("unmatchedReturnedRules") or []
        raw = rule_results.get("raw") or {}
        mode = str(rule_results.get("mode") or "remote_api")

        if status == "no_rule_configs":
            return [
                VerificationItem(
                    id="verify_rule_engine_no_config",
                    name="规则引擎校验未启用",
                    method="GoRules 规则引擎联调",
                    status=VerificationStatus.WARNING,
                    description="当前没有启用任何规则校验配置，本轮未执行规则引擎校验。",
                    source="rule_engine",
                    engineStatus=status,
                    detail={"mode": mode},
                )
            ]

        if status == "not_connected":
            return [
                VerificationItem(
                    id="verify_rule_engine_not_connected",
                    name="规则引擎未接入",
                    method="GoRules 规则引擎联调",
                    status=VerificationStatus.WARNING,
                    description="规则引擎当前未接入，本轮仅使用模型抽取和基础校验结果。",
                    source="rule_engine",
                    engineStatus=status,
                    detail={"mode": mode},
                )
            ]

        if status == "engine_error":
            return [
                VerificationItem(
                    id="verify_rule_engine_error",
                    name="规则引擎调用失败",
                    method="GoRules 规则引擎联调",
                    status=VerificationStatus.WARNING,
                    description=str(raw.get("message") or "规则引擎调用失败，本轮未能完成规则校验。"),
                    source="rule_engine",
                    engineStatus=status,
                    detail={"mode": mode},
                )
            ]

        items: list[VerificationItem] = []
        if configured_rules:
            if matched_rules:
                items.append(
                    VerificationItem(
                        id="verify_rule_engine_summary",
                        name="规则引擎执行结果",
                        method="GoRules 规则引擎联调",
                        status=VerificationStatus.WARNING,
                        description=f"规则引擎已执行，本轮共命中 {len(matched_rules)} 条规则。",
                        source="rule_engine",
                        engineStatus=status,
                        detail={"mode": mode, "matchedRuleCount": len(matched_rules)},
                    )
                )
            else:
                items.append(
                    VerificationItem(
                        id="verify_rule_engine_summary",
                        name="规则引擎执行结果",
                        method="GoRules 规则引擎联调",
                        status=VerificationStatus.PASS,
                        description="规则引擎已执行，当前未命中已配置规则。",
                        source="rule_engine",
                        engineStatus=status,
                        detail={"mode": mode, "matchedRuleCount": 0},
                    )
                )

        if missing_rules:
            missing_text = "；".join(
                f"{item.get('name', '未命名配置')} ({item.get('ruleId', 'unknown')})"
                for item in missing_rules
                if isinstance(item, dict)
            )
            items.append(
                VerificationItem(
                    id="verify_rule_engine_missing_configured_rules",
                    name="规则配置未在引擎中生效",
                    method="规则配置 / 引擎规则目录比对",
                    status=VerificationStatus.WARNING,
                    description=f"发现 {len(missing_rules)} 条规则配置在当前 GoRules 规则目录中不存在：{missing_text}。",
                    source="rule_engine",
                    engineStatus="missing_configured_rules",
                    detail={"missingConfiguredRules": missing_rules},
                )
            )

        if unmatched_rules:
            unmatched_text = "；".join(
                f"{item.get('ruleName') or item.get('ruleId') or '未命名规则'}"
                for item in unmatched_rules
                if isinstance(item, dict)
            )
            items.append(
                VerificationItem(
                    id="verify_rule_engine_unmatched_rules",
                    name="规则引擎返回了未绑定的规则",
                    method="规则返回映射检查",
                    status=VerificationStatus.WARNING,
                    description=f"规则引擎返回了 {len(unmatched_rules)} 条未绑定到当前审计配置的规则：{unmatched_text}。",
                    source="rule_engine",
                    engineStatus="unmatched_returned_rules",
                    detail={"unmatchedReturnedRules": unmatched_rules},
                )
            )

        return items

    @staticmethod
    def _build_engine_rule_items(
        clauses: list[ClauseTag],
        rule_results: dict[str, Any],
    ) -> list[VerificationItem]:
        matched_rules = rule_results.get("matchedRules") or []
        if not isinstance(matched_rules, list):
            return []
        clause_ids = {clause.id for clause in clauses}
        items: list[VerificationItem] = []
        for index, item in enumerate(matched_rules, start=1):
            if not isinstance(item, dict):
                continue
            matched_clause_ids = [
                clause_id
                for clause_id in item.get("evidenceClauseIds", [])
                if isinstance(clause_id, str) and clause_id in clause_ids
            ]
            severity = str(item.get("severity") or "medium").lower()
            status = VerificationStatus.WARNING if severity in {"low", "medium"} else VerificationStatus.FAIL
            items.append(
                VerificationItem(
                    id=f"verify_rule_engine_{index:03d}",
                    name=str(item.get("ruleName") or item.get("ruleId") or "规则引擎命中"),
                    method="GoRules 规则校验",
                    status=status,
                    description=str(item.get("reason") or "规则引擎命中了一个待复核条件。"),
                    relatedClauseIds=matched_clause_ids,
                    needExternalTool=False,
                    source="rule_engine",
                    configId=str(item.get("configId") or "") or None,
                    ruleId=str(item.get("ruleId") or "") or None,
                    engineStatus="hit",
                    detail={"dependsOn": item.get("dependsOn") or []},
                )
            )
        return items

    async def _request_verification_narratives(
        self,
        items: list[VerificationItem],
        clauses: list[ClauseTag],
        audit_focuses: list[AuditFocus],
    ) -> dict[str, Any]:
        clause_payload = [
            {
                "id": clause.id,
                "label": clause.label,
                "coreLabel": clause.coreLabel,
                "page": clause.page,
                "summary": clause.summary,
                "confidence": clause.confidence,
            }
            for clause in clauses[:24]
        ]
        audit_payload = [
            {
                "id": audit.id,
                "title": audit.title,
                "riskLevel": audit.riskLevel,
                "evidenceClauseIds": audit.evidenceClauseIds,
            }
            for audit in audit_focuses[:24]
        ]
        verify_payload = [item.model_dump() for item in items]
        prompt = build_verification_narrative_prompt(clause_payload, audit_payload, verify_payload)
        return await self.qwen_service.chat_json(
            system_prompt=prompt.system,
            user_prompt=prompt.user,
            schema={"type": "object"},
            timeout=90,
        )

    @staticmethod
    def _merge_narratives(
        items: list[VerificationItem],
        payload: dict[str, Any],
    ) -> list[VerificationItem]:
        descriptions = {
            item.get("id"): item
            for item in payload.get("verificationItems", [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        merged: list[VerificationItem] = []
        for item in items:
            override = descriptions.get(item.id)
            if override:
                description = str(override.get("description") or item.description).strip()
                method = str(override.get("method") or item.method).strip()
                merged.append(item.model_copy(update={"description": description, "method": method}))
            else:
                merged.append(item)
        return merged
