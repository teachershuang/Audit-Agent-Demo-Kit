from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TemplateCatalogItem(BaseModel):
    template_id: str
    template_name: str
    category_lv1: str | None = None
    category_lv2: str | None = None
    start_page: int = 1
    end_page: int = 1
    preview_page: int | None = None
    clause_count: int | None = None
    signature: str | None = None
    key_clause_titles: list[str] = Field(default_factory=list)
    auto_variant_cues: list[str] = Field(default_factory=list)
    auto_variant_summary: str | None = None
    usage_profile: str | None = None
    usage_profile_basis: list[str] = Field(default_factory=list)
    usage_profile_summary: str | None = None
    same_name_index: int | None = None
    same_name_total: int | None = None
    disambiguation_label: str | None = None


class DocumentRecord(BaseModel):
    id: str
    name: str
    doc_type: str
    category: str | None = None
    version: str = "v1"
    issuer: str | None = None
    status: str = "effective"
    effective_date: str | None = None
    effective_ts: int = 0
    abolish_date: str | None = None
    abolish_ts: int = 99991231
    replaced_by: str | None = None
    file_hash: str
    source_file: str
    confidential_level: str = "internal"
    created_at: str
    template_count: int = 0
    source_kind: str = "file"
    current_version_flag: bool = True
    template_catalog: list[TemplateCatalogItem] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class DocumentStatusPatch(BaseModel):
    status: str


class DocumentAbolishRequest(BaseModel):
    abolish_date: str | None = None
    abolish_ts: int | None = None


class DocumentPatchRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    version: str | None = None
    issuer: str | None = None
    template_catalog: list[TemplateCatalogItem] | None = None


class DocumentUploadResponse(BaseModel):
    document: DocumentRecord
    clause_count: int
    rule_count: int = 0
    rules: list[dict[str, Any]] = Field(default_factory=list)
