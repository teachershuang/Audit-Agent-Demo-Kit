from __future__ import annotations

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
        clause_payload = [
            {
                "id": item.id,
                "label": item.label,
                "title": item.title,
                "summary": item.summary,
                "page": item.page,
                "confidence": item.confidence,
            }
            for item in clauses
        ]

        payload = await self.qwen_service.chat_json(
            system_prompt=(
                "你是审计风控辅助分析 Agent。"
                "请基于合同解析结果、条款标签、关键信息和关系配置，生成审计关注事项。"
                "不能输出最终审计结论，只能输出关注事项、疑似风险、待核验事项。"
                "每个结果都必须写明原因、证据条款、位置、当前依据、建议工具和人工复核建议。"
            ),
            user_prompt=(
                f"合同章节：{json.dumps([item.model_dump() for item in sections], ensure_ascii=False)}\n"
                f"合同条款：{json.dumps(clause_payload, ensure_ascii=False)}\n"
                f"关键信息：{json.dumps([item.model_dump() for item in key_facts], ensure_ascii=False)}\n"
                f"关系配置：{json.dumps([item.model_dump() for item in relations], ensure_ascii=False)}\n"
                "请输出 auditFocuses 数组，evidenceClauseIds 必须使用已给定的 clause id。"
                "至少覆盖付款条件、验收标准、违约责任、合同主体完整性、账户信息、供应商关系或疑似关联关系。"
                "字段名必须使用以下英文键名："
                "id,title,riskLevel,reason,evidenceClauseIds,locationText,confidence,dependsOn,currentBasis,futureTools,modelOnly,humanReviewSuggestion。"
                "riskLevel 只能是 low、medium、high、pending_verification。"
            ),
            schema={"type": "object"},
        )

        raw_items = self._pick_first_array(payload, ["auditFocuses", "关注事项", "audit_focuses"])
        valid_clause_ids = {item.id for item in clauses}
        audit_focuses: list[AuditFocus] = []
        for index, item in enumerate(raw_items, start=1):
            clause_ids = [
                clause_id
                for clause_id in self._to_list(
                    item.get("evidenceClauseIds") or item.get("evidence_clause_ids") or item.get("关联条款")
                )
                if clause_id in valid_clause_ids
            ]
            if not clause_ids:
                continue

            audit_focuses.append(
                AuditFocus(
                    id=str(item.get("id") or f"audit_{index:03d}").strip(),
                    title=str(item.get("title") or item.get("名称") or f"关注事项 {index}").strip(),
                    riskLevel=self._normalize_risk_level(item.get("riskLevel") or item.get("风险等级")),
                    reason=str(item.get("reason") or item.get("原因") or "").strip(),
                    evidenceClauseIds=clause_ids,
                    locationText=str(item.get("locationText") or item.get("位置") or "").strip(),
                    confidence=self._clamp_confidence(item.get("confidence") or item.get("置信度") or 0.75),
                    dependsOn=self._to_list(item.get("dependsOn") or item.get("依赖数据")),
                    currentBasis=str(item.get("currentBasis") or item.get("当前依据") or "").strip(),
                    futureTools=self._to_list(item.get("futureTools") or item.get("建议工具")),
                    modelOnly=self._to_bool(item.get("modelOnly", True)),
                    humanReviewSuggestion=str(
                        item.get("humanReviewSuggestion") or item.get("复核建议") or ""
                    ).strip(),
                )
            )
        return audit_focuses

    @staticmethod
    def _pick_first_array(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _to_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.replace("；", "、").replace("，", "、").split("、") if part.strip()]
        return []

    @staticmethod
    def _normalize_risk_level(value: Any) -> str:
        mapping = {
            "低": "low",
            "中": "medium",
            "高": "high",
            "待核验": "pending_verification",
            "pending": "pending_verification",
            "pending_verification": "pending_verification",
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        return mapping.get(str(value or "pending_verification").strip(), "pending_verification")

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.5
        return max(0.01, min(score, 0.99))

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "否"}
        return bool(value)
