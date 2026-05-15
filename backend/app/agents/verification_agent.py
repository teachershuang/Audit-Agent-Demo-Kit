from __future__ import annotations

import json
from typing import Any

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
    ) -> list[VerificationItem]:
        items = self._build_rule_items(sections=sections, clauses=clauses, audit_focuses=audit_focuses)
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
                        method="条款标签识别 + 原文证据定位",
                        status=VerificationStatus.PASS,
                        description=f"已识别到 {label}，并建立原文证据映射。",
                        relatedClauseIds=[clause.id],
                        relatedEvidenceIds=[clause.evidenceId] if clause.evidenceId else [],
                    )
                )
            else:
                items.append(
                    VerificationItem(
                        id=f"verify_required_{index:03d}",
                        name=f"{label}完整性校验",
                        method="条款标签识别 + 原文证据定位",
                        status=VerificationStatus.FAIL,
                        description=f"未识别到 {label} 条款，建议人工复核合同原文。",
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
                    method="关键词命中 + 语义对照",
                    status=status,
                    description=f"命中关键词：{'、'.join(hits) if hits else '未命中核心关键词'}。",
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
                    description=f"发现 {len(low_confidence)} 项低置信度条款，建议重点复核。",
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
                )
            )

        if sections:
            items.append(
                VerificationItem(
                    id="verify_structure",
                    name="章节结构校验",
                    method="章节识别 + 页码映射",
                    status=VerificationStatus.PASS,
                    description=f"共识别 {len(sections)} 个章节，并完成页码映射。",
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
        return await self.qwen_service.chat_json(
            system_prompt=(
                "你是合同审计校验说明 Agent。"
                "请把结构化校验结果改写成用户可读、业务可理解的校验说明。"
                "不能改变校验结论的状态，只能优化说明文字和人工复核建议。"
                "输出必须是中文。"
            ),
            user_prompt=(
                f"条款摘要：\n{json.dumps(clause_payload, ensure_ascii=False)}\n"
                f"关注事项：\n{json.dumps(audit_payload, ensure_ascii=False)}\n"
                f"校验结构：\n{json.dumps(verify_payload, ensure_ascii=False)}\n"
                "请返回 JSON 对象，顶层字段为 `verificationItems`。"
                "每个 verification item 包含：id, description, method。"
            ),
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
