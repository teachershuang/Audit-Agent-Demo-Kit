from __future__ import annotations

import re


def clean_text(text: str) -> str:
    normalized = text.replace("\u3000", " ").replace("\xa0", " ").replace("\u200b", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", clean_text(text))
