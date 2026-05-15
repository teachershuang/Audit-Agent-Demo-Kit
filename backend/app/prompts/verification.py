from __future__ import annotations

import json
from typing import Any

from app.prompts.types import PromptBundle


def build_verification_narrative_prompt(
    clause_payload: list[dict[str, Any]],
    audit_payload: list[dict[str, Any]],
    verify_payload: list[dict[str, Any]],
) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是合同审计校验说明 Agent。"
            "请把结构化校验结果改写成用户可读、业务可理解的校验说明。"
            "不能改变校验结论的状态，只能优化说明文字和人工复核建议。"
            "输出必须是中文。"
        ),
        user=(
            f"条款摘要：\n{json.dumps(clause_payload, ensure_ascii=False)}\n"
            f"关注事项：\n{json.dumps(audit_payload, ensure_ascii=False)}\n"
            f"校验结构：\n{json.dumps(verify_payload, ensure_ascii=False)}\n"
            "请返回 JSON 对象，顶层字段为 `verificationItems`。"
            "每个 verification item 包含：id, description, method。"
        ),
    )
