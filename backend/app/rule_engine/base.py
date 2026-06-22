from __future__ import annotations

from pydantic import BaseModel, Field


class RuleHit(BaseModel):
    rule_id: str
    rule_name: str
    severity: str
    department: str
    problem: str
    basis_policy: list[str] = Field(default_factory=list)
    basis_template: str | None = None
    suggestion: str
    confidence: float
    clause_location: str = ""
