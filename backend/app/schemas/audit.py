from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PENDING_VERIFICATION = "pending_verification"


class VerificationStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    EXTERNAL_PENDING = "external_pending"


class AuditFocus(BaseModel):
    id: str
    title: str
    riskLevel: RiskLevel
    reason: str
    evidenceClauseIds: list[str] = Field(default_factory=list)
    locationText: str
    confidence: float
    dependsOn: list[str] = Field(default_factory=list)
    currentBasis: str
    futureTools: list[str] = Field(default_factory=list)
    modelOnly: bool = True
    humanReviewSuggestion: str


class VerificationItem(BaseModel):
    id: str
    name: str
    method: str
    status: VerificationStatus
    description: str
    relatedClauseIds: list[str] = Field(default_factory=list)
    relatedEvidenceIds: list[str] = Field(default_factory=list)
    needExternalTool: bool = False
