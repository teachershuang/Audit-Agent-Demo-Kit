from __future__ import annotations

import json


def build_vl_ocr_prompt() -> str:
    return (
        "你正在阅读一页中文扫描合同。"
        "请只做 OCR 与阅读顺序还原，不要总结，不要解释，不要翻译。"
        "返回 JSON，对象包含 `full_text` 和 `paragraphs`。"
        "`paragraphs` 必须是按自然阅读顺序排列的段落数组，只能基于图片中可见文字。"
    )


def build_text_anchor_system_prompt() -> str:
    return (
        "你负责把合同语义段落回锚到 OCR 行。"
        "每个段落只能映射到输入里真实存在的连续 lineIds。"
        "不要编造 lineIds，不要输出英文。"
    )


def build_text_anchor_user_prompt(line_payload: list[dict[str, str]], paragraph_payload: list[str]) -> str:
    return (
        f"OCR lines: {json.dumps(line_payload, ensure_ascii=False)}\n"
        f"Semantic paragraphs: {json.dumps(paragraph_payload, ensure_ascii=False)}\n"
        "请返回 JSON 对象，顶层字段为 `groups`。"
        "每个 group 包含 `paragraph` 和 `lineIds`。"
    )


def build_vl_fallback_prompt() -> str:
    return (
        "You are an OCR assistant for Chinese contracts. Read the page in natural reading order and "
        "return a JSON object with two fields: `full_text` and `paragraphs`. "
        "`paragraphs` must be an ordered array of paragraph strings. "
        "Do not invent content that is not visible in the image."
    )
