from __future__ import annotations

import json
from typing import Any

from app.prompts.types import PromptBundle


def build_audit_focus_prompt(
    section_payload: list[dict[str, Any]],
    clause_payload: list[dict[str, Any]],
    fact_payload: list[dict[str, Any]],
    relation_payload: list[dict[str, Any]],
    focus_hint: str,
) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是审计风控辅助分析 Agent。"
            "请基于合同章节、条款、关键信息和用户配置的审计配置项，生成审计关注方向。"
            "不能输出最终审计结论，只能输出关注方向、疑似风险或待核验事项。"
            "你既要响应用户配置的审计配置项，也可以主动发现新的关注方向。"
            "对于内部关联交易、供应商关系、账户异常等，必须使用“疑似”“待核验”“建议接入外部数据确认”的措辞。"
            "所有输出必须是中文。"
        ),
        user=(
            f"关注主题：{focus_hint}\n"
            f"章节：\n{json.dumps(section_payload, ensure_ascii=False)}\n"
            f"条款：\n{json.dumps(clause_payload, ensure_ascii=False)}\n"
            f"关键信息：\n{json.dumps(fact_payload, ensure_ascii=False)}\n"
            f"审计配置：\n{json.dumps(relation_payload, ensure_ascii=False)}\n"
            "请返回 JSON 对象，顶层字段为 `auditFocuses`。"
            "每个关注项包含：title, focusSource, matchedRelationIds, riskLevel, reason, evidenceClauseIds, "
            "locationText, confidence, dependsOn, currentBasis, futureTools, modelOnly, humanReviewSuggestion。"
            "focusSource 只能是 `user_rule_check`、`user_relation_check`、`user_external_check` 或 `agent_discovered`。"
            "matchedRelationIds 只能引用输入中的审计配置 id。"
            "如果某个关注项明确来自用户配置，请尽量给出对应的 matchedRelationIds。"
        ),
    )
