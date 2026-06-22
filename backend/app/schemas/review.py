from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ContractSchema(BaseModel):
    contract_id: str
    source_task_id: str
    detected_category: str
    matched_template_id: str | None = None
    matched_template_name: str | None = None
    fields: dict[str, str | None] = Field(default_factory=dict)
    clauses: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ReviewIssue(BaseModel):
    id: str
    severity: str
    department: str
    clause_location: str
    problem: str
    basis_policy: list[str] = Field(default_factory=list)
    basis_policy_details: list[dict[str, Any]] = Field(default_factory=list)
    basis_template: str | None = None
    basis_template_detail: dict[str, Any] | None = None
    source_rule_id: str | None = None
    source_rule_name: str | None = None
    suggestion: str
    confidence: float
    extra: dict[str, Any] = Field(default_factory=dict)


class ReviewReport(BaseModel):
    contract_id: str
    status: str
    matched_template: dict[str, Any] | None = None
    detected_category: str
    summary: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    created_at: str


class ReviewRequest(BaseModel):
    source_task_id: str
    selected_template_id: str | None = None


class ReviewResponse(BaseModel):
    contract_id: str
    status: str
    matched_template: dict[str, Any] | None = None
    detected_category: str
    issue_count: int


class SourceTaskSummary(BaseModel):
    task_id: str
    file_name: str
    status: str
    created_at: str


class ReviewTaskRecord(BaseModel):
    task_id: str
    source_task_id: str
    selected_template_id: str | None = None
    status: str
    message: str
    created_at: str
    updated_at: str
    contract_id: str | None = None
    issue_count: int | None = None
    detected_category: str | None = None
    matched_template: dict[str, Any] | None = None
    error: str | None = None
