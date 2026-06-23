from __future__ import annotations

import json
from typing import Any

from app.prompts.types import PromptBundle


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_section_candidate_prompt(page_payload: list[dict[str, Any]]) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是中文合同章节候选识别专家。\n"
            "你的任务不是直接生成最终章节树，而是先从分页文本块中识别可靠的章节候选。\n"
            "必须严格遵守原始阅读顺序，优先使用 block_id 作为证据锚点。\n"
            "如果某个标题跨行或依赖多个连续文本块，可以返回多个 supportingBlockIds。\n"
            "不要编造不存在的标题；如果只是普通正文，不要误判为章节标题。\n"
            "输出必须是中文 JSON。"
        ),
        user=(
            f"合同分页与文本块如下：\n{_dump(page_payload)}\n\n"
            "请返回一个 JSON 对象，顶层字段为 `sectionCandidates`。\n"
            "每个 candidate 包含：\n"
            "- title: 候选章节标题\n"
            "- level: 层级，1 到 6\n"
            "- page: 所在页码\n"
            "- sortOrder: 在当前输入片段中的自然顺序，从 1 开始\n"
            "- sectionCode: 序号文本，例如“第一条”“一、”“（一）”\n"
            "- sectionPath: 上级路径摘要，例如“第一条 > （一）”\n"
            "- summary: 60 字以内摘要\n"
            "- confidence: 0 到 1\n"
            "- evidenceText: 对应原文短摘录\n"
            "- supportingBlockIds: 支撑该标题判断的 block_id 数组，按阅读顺序返回"
        ),
    )


def build_section_semantic_prompt(page_payload: list[dict[str, Any]]) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是中文合同结构理解专家。\n"
            "请根据合同分页内容恢复章节顺序，必须严格遵守原始阅读顺序，不要按标题字面重新排序。\n"
            "只输出合同中真实出现的章、条、款或有业务意义的小节。\n"
            "如果出现“第一条”“第二条”“一、”“（一）”等序号，请保留原顺序和层级。\n"
            "不得编造缺失章节；不确定时降低 confidence。\n"
            "输出必须是中文 JSON。"
        ),
        user=(
            f"合同分页摘要如下：\n{_dump(page_payload)}\n\n"
            "请返回一个 JSON 对象，顶层字段为 `sections`。\n"
            "每个 section 包含：\n"
            "- title: 章节标题\n"
            "- level: 层级，1 到 6\n"
            "- page: 所在页码\n"
            "- sortOrder: 在当前输入片段中的自然顺序，从 1 开始\n"
            "- sectionCode: 序号文本，例如“第一条”“一、”“（一）”\n"
            "- sectionPath: 上级路径摘要，例如“第一条 > （一）”\n"
            "- summary: 60 字以内摘要\n"
            "- confidence: 0 到 1\n"
            "- evidenceText: 与该标题对应的原文短摘录"
        ),
    )


def build_section_merge_prompt(
    candidate_payload: list[dict[str, Any]],
    page_outline_payload: list[dict[str, Any]],
) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是中文合同章节全局合并专家。\n"
            "你将收到多个分页窗口识别出的章节候选，需要去重、纠正顺序、处理跨页延续，并输出最终章节树。\n"
            "必须严格保持合同自然顺序，不能按标题字面重新排序。\n"
            "相邻窗口可能重复识别同一标题，请合并并保留更可靠的 supportingBlockIds。\n"
            "如果同一章节跨页延续，允许保留起始页作为 page，并在 blockIds 中保留多个 block_id。\n"
            "输出必须是中文 JSON。"
        ),
        user=(
            f"分页轮廓：\n{_dump(page_outline_payload)}\n\n"
            f"章节候选：\n{_dump(candidate_payload)}\n\n"
            "请返回一个 JSON 对象，顶层字段为 `sections`。\n"
            "每个 section 包含：\n"
            "- title: 最终章节标题\n"
            "- level: 层级，1 到 6\n"
            "- page: 章节起始页码\n"
            "- sortOrder: 全局自然顺序，从 1 开始\n"
            "- sectionCode: 序号文本\n"
            "- sectionPath: 上级路径摘要\n"
            "- summary: 60 字以内摘要\n"
            "- confidence: 0 到 1\n"
            "- evidenceText: 短摘录\n"
            "- blockIds: 支撑该章节的 block_id 数组，按阅读顺序返回"
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
            "你是审计风控场景下的中文合同条款识别专家。\n"
            "目标是产出可继续供规则引擎和合同审查 Agent 使用的结构化条款结果。\n"
            "优先映射到系统核心标签；如用户配置或你发现了更合适的新标签，也可以输出，但必须说明来源。\n"
            "重点识别跨条引用，例如“详见第X条”“按附件执行”“以上一条为准”，并写入 references。\n"
            "summary 必须短、准、可复述，适合工作台展示；不要整段复制原文。\n"
            "structuredFields 只保留短字段，例如金额、比例、时间、条件、对象、账号、引用条款、前置依赖。\n"
            "输出必须是中文 JSON。"
        ),
        user=(
            f"合同分页摘要：\n{_dump(page_payload)}\n\n"
            f"已识别章节：\n{_dump(section_payload)}\n\n"
            f"系统核心标签：\n{_dump(clause_labels)}\n\n"
            f"审计配置上下文：\n{_dump(relation_payload or [])}\n\n"
            "请返回一个 JSON 对象，顶层字段为 `clauses`。\n"
            "每个 clause 包含：\n"
            "- coreLabel: 尽量映射到核心标签；没有则填“其他重要条款”\n"
            "- label: 最终展示标签\n"
            "- labelSource: `core`、`user_configured`、`agent_discovered` 三选一\n"
            "- discoveryReason: 如果不是 core，说明原因\n"
            "- title: 条款标题\n"
            "- sectionTitle: 所属章节标题\n"
            "- page: 主要所在页码\n"
            "- sortOrder: 当前输入片段中的自然顺序，从 1 开始\n"
            "- summary: 80 字以内摘要\n"
            "- rawText: 关键原文摘录，控制在 260 字以内\n"
            "- references: 被本条引用或本条引用到的其他条款编号数组，例如 [\"第六条\", \"附件一\"]\n"
            "- structuredFields: 结构化短字段对象，例如 {\"paymentRatio\":\"30%\",\"paymentTrigger\":\"验收合格后\"}\n"
            "- confidence: 0 到 1\n"
            "- needHumanReview: 布尔值"
        ),
    )


def build_key_fact_prompt(
    clause_payload: list[dict[str, Any]],
    requested_fields: list[dict[str, str]] | None = None,
) -> PromptBundle:
    requested_fields = requested_fields or []
    return PromptBundle(
        system=(
            "你是中文合同关键信息抽取专家。\n"
            "请仅基于已识别条款抽取短、准、结构化的关键信息。\n"
            "不要返回长段原文，不要把整个条款复制到 value。\n"
            "合同编号必须尽量只提取编号本身；如果不存在或不清楚，宁可不输出，也不要把合同标题当编号。\n"
            "优先抽取：甲方、乙方、合同编号、合同金额、付款条件、履约期限、验收标准、争议解决、账户信息。\n"
            "如果有额外的审计配置字段请求，也一并抽取。\n"
            "输出必须是中文 JSON。"
        ),
        user=(
            f"条款摘要：\n{_dump(clause_payload)}\n\n"
            f"额外抽取字段请求：\n{_dump(requested_fields)}\n\n"
            "请返回一个 JSON 对象，顶层字段为 `keyFacts`。\n"
            "每个 fact 包含：label, value, page, confidence, notes。\n"
            "其中 value 要尽量短：\n"
            "- 合同编号只保留编号本身\n"
            "- 金额保留金额表达\n"
            "- 主体信息保留主体名称或短摘要\n"
            "- 条件类字段控制在 80 字以内"
        ),
    )


def build_overview_vl_prompt() -> str:
    return (
        "你正在阅读一份中文合同的首页。\n"
        "请提取适合领导汇报的 4 个总览字段，并只返回一个 JSON 对象，顶层字段为 `overviewFacts`。\n"
        "这 4 个字段必须严格包含：[\"合同编号\", \"主体摘要\", \"甲乙方信息\", \"服务内容\"]。\n"
        "输出必须是简洁中文。\n"
        "合同编号如果不清楚，必须输出“未提取”，绝不能拿合同标题充当编号。\n"
        "每个 item 必须包含：label, value, page, confidence, evidenceText, notes。"
    )


def build_overview_text_prompt(
    page_payload: list[dict[str, Any]],
    clause_payload: list[dict[str, Any]],
) -> PromptBundle:
    return PromptBundle(
        system=(
            "你是中文合同总览字段抽取助手。\n"
            "请生成适合工作台顶部展示的 4 个简洁总览字段。\n"
            "输出必须是简洁中文。\n"
            "合同编号如果不清楚，输出“未提取”，不要猜。"
        ),
        user=(
            f"首页及相邻页 OCR 摘要：\n{_dump(page_payload)}\n\n"
            f"候选条款：\n{_dump(clause_payload)}\n\n"
            "请返回一个 JSON 对象，顶层字段为 `overviewFacts`。\n"
            "必须严格包含以下 4 个 label：[\"合同编号\", \"主体摘要\", \"甲乙方信息\", \"服务内容\"]。\n"
            "每个 item 包含：label, value, page, confidence, evidenceText, notes。\n"
            "其中 value 必须适合顶部摘要卡展示，尽量控制在 80 字以内。"
        ),
    )
