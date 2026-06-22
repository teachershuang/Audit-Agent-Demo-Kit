from __future__ import annotations

from pydantic import BaseModel, Field


class ClauseRecord(BaseModel):
    id: str
    document_id: str
    doc_type: str
    template_id: str | None = None
    template_name: str | None = None
    category_lv1: str | None = None
    category_lv2: str | None = None
    clause_no: str | None = None
    title: str
    clause_type: str = "general"
    content: str
    page_start: int = 1
    page_end: int = 1
    status: str = "effective"
    effective_ts: int = 0
    abolish_ts: int = 99991231
    risk_tags: list[str] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)


class ClauseSearchRequest(BaseModel):
    query: str
    top_k: int = 10
    doc_type: str | None = None
    category_lv1: str | None = None
    category_lv2: str | None = None
    template_id: str | None = None
