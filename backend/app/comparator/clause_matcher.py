from __future__ import annotations

import re
from difflib import SequenceMatcher


def normalize_title(text: str) -> str:
    return re.sub(r"[\s:：、，。；\-（）()\[\]]+", "", text).lower()


def clause_similarity(left_title: str, left_content: str, right_title: str, right_content: str) -> float:
    title_score = SequenceMatcher(None, normalize_title(left_title), normalize_title(right_title)).ratio()
    content_score = SequenceMatcher(None, left_content[:240], right_content[:240]).ratio()
    return title_score * 0.65 + content_score * 0.35
