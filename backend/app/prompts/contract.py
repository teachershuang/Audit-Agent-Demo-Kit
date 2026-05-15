from __future__ import annotations

import json
from typing import Any

from app.prompts.types import PromptBundle


def build_section_semantic_prompt(page_payload: list[dict[str, Any]]) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是中文合同结构理解专家。"
            "请仅根据输入的合同页摘要，识别真实存在的章节或条款层级标题。"
            "不要编造不存在的标题，不要翻译成英文。"
            "优先输出主章节，再输出有业务意义的小节。"
        ),
        user=(
            f"合同页摘要如下：\n{json.dumps(page_payload, ensure_ascii=False)}\n"
            "请返回 JSON 对象，顶层字段为 `sections`。"
            "每个 section 包含：title, level, page, summary, confidence, evidenceText。"
        ),
    )


def build_clause_semantic_prompt(
    page_payload: list[dict[str, Any]],
    section_payload: list[dict[str, Any]],
    clause_labels: list[str],
    relation_payload: list[dict[str, Any]] | None = None,
) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是审计风控场景下的中文合同条款识别专家。"
            "请优先使用系统核心标签，但如果发现明显重要且不适合核心标签的条款，可以新增 Agent 发现标签。"
            f"核心标签集合：{', '.join(clause_labels)}。"
            "如果用户关系配置里出现了额外关注主题，可以将其作为发现线索，但不要把关系配置硬编码成条款结果。"
            "输出必须是中文，不要翻译，不要编造。"
        ),
        user=(
            f"合同页摘要：\n{json.dumps(page_payload, ensure_ascii=False)}\n"
            f"已识别章节：\n{json.dumps(section_payload, ensure_ascii=False)}\n"
            f"关系配置上下文：\n{json.dumps(relation_payload or [], ensure_ascii=False)}\n"
            "请返回 JSON 对象，顶层字段为 `clauses`。"
            "每个 clause 包含："
            "coreLabel, label, labelSource, discoveryReason, title, summary, rawText, page, confidence, needHumanReview。"
            "其中 labelSource 只能是 `core`、`user_configured` 或 `agent_discovered`。"
        ),
    )


def build_key_fact_prompt(clause_payload: list[dict[str, Any]]) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是中文合同关键信息抽取专家。"
            "请仅基于已识别条款抽取关键事实，不要编造。"
            "优先抽取：甲方、乙方、合同编号、合同金额、付款条件、履约期限、验收标准、争议解决、账户信息。"
        ),
        user=(
            f"条款摘要：\n{json.dumps(clause_payload, ensure_ascii=False)}\n"
            "请返回 JSON 对象，顶层字段为 `keyFacts`。"
            "每个 fact 包含：label, value, page, confidence, notes。"
        ),
    )


def build_overview_vl_prompt() -> str:
    return (
        "你正在阅读一份中文合同的首页。"
        "请提取领导汇报场景下最重要的 4 个总览字段，并只返回一个 JSON 对象，顶层字段为 `overviewFacts`。"
        "这 4 个字段必须严格包含："
        "[\"合同编号\", \"主体摘要\", \"甲乙方信息\", \"服务内容\"]。"
        "输出必须是中文，表达要简洁专业。"
        "如果合同编号没有在图片中清晰出现，必须输出“未提取”，不要猜测。"
        "每个 item 必须包含：label, value, page, confidence, evidenceText, notes。"
    )


def build_overview_text_prompt(
    page_payload: list[dict[str, Any]],
    clause_payload: list[dict[str, Any]],
) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是中文合同总览信息提取助手。"
            "请提取领导汇报场景下的四个总览字段。"
            "输出必须是中文且简洁。"
            "不要编造缺失值；如果合同编号不清晰，输出“未提取”。"
        ),
        user=(
            f"首页及相邻页 OCR 摘要：\n{json.dumps(page_payload, ensure_ascii=False)}\n"
            f"候选条款：\n{json.dumps(clause_payload, ensure_ascii=False)}\n"
            "请返回一个 JSON 对象，顶层字段为 `overviewFacts`。"
            "必须严格包含以下四个 label："
            "[\"合同编号\", \"主体摘要\", \"甲乙方信息\", \"服务内容\"]。"
            "每个 item 必须包含：label, value, page, confidence, evidenceText, notes。"
        ),
    )
