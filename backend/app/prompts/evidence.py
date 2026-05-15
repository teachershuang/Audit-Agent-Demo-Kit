from __future__ import annotations

import json
from typing import Any

from app.prompts.types import PromptBundle


def build_grounding_prompt(
    batch: list[dict[str, Any]],
    page_scope: list[dict[str, Any]],
    top_key: str,
    item_kind: str,
) -> PromptBundle:
    return PromptBundle(
        system=(
            "You are grounding already-identified contract items back to OCR blocks. "
            "Do not reinterpret the item type. "
            "Only map each candidate to the best supporting blockIds from the provided OCR blocks. "
            "You may return multiple non-contiguous blockIds when the evidence crosses pages or is split. "
            "Do not invent blockIds."
        ),
        user=(
            f"Candidates ({item_kind}):\n{json.dumps(batch, ensure_ascii=False)}\n"
            f"OCR page scope:\n{json.dumps(page_scope, ensure_ascii=False)}\n"
            f"Return one JSON object with top-level key `{top_key}`. "
            "Each item must include candidateId and blockIds."
        ),
    )
