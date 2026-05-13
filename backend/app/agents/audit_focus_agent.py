from __future__ import annotations

from typing import Iterable

from app.mock.sample_result import build_mock_audit_focuses
from app.schemas.audit import AuditFocus
from app.schemas.contract import ClauseTag, ContractSection
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
    ) -> list[AuditFocus]:
        enabled_relations = [item.id for item in relations if item.enabled]
        if self.qwen_service.is_mock:
            return build_mock_audit_focuses(enabled_relations)

        try:
            system_prompt = (
                "你是审计风控辅助分析 Agent。请基于合同解析结果、条款标签、用户配置的关系类型，"
                "生成审计关注方向。不能输出最终审计结论，只能输出关注方向、疑似风险、待核验事项。"
            )
            clause_payload = [
                {
                    "label": item.label,
                    "summary": item.summary,
                    "page": item.page,
                    "evidenceId": item.evidenceId,
                }
                for item in clauses
            ]
            relation_payload = [item.model_dump() for item in relations]
            user_prompt = (
                f"合同章节：{[item.model_dump() for item in sections]}\n"
                f"合同条款：{clause_payload}\n"
                f"关系配置：{relation_payload}\n"
                "请输出 auditFocuses 数组。"
            )
            schema = {
                "type": "object",
                "properties": {
                    "auditFocuses": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
                "required": ["auditFocuses"],
            }
            payload = await self.qwen_service.chat_json(system_prompt, user_prompt, schema)
            return [AuditFocus.model_validate(item) for item in payload["auditFocuses"]]
        except Exception:
            return build_mock_audit_focuses(enabled_relations)

    @staticmethod
    def clause_titles(clauses: Iterable[ClauseTag]) -> list[str]:
        return [item.title for item in clauses]
