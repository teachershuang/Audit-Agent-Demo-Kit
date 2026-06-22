from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuleRecord(BaseModel):
    id: str
    name: str
    enabled: bool = False
    rule_type: str = "legal"
    contract_categories: list[str] = Field(default_factory=list)
    severity: str = "must_modify"
    basis_policy: list[str] = Field(default_factory=list)
    logic: dict[str, Any] = Field(default_factory=dict)
    suggestion_template: str
    department: str = "legal"
    source_document_id: str | None = None
    status: str = "draft"


class RulePatchRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    severity: str | None = None
    logic: dict[str, Any] | None = None
    suggestion_template: str | None = None
    department: str | None = None
