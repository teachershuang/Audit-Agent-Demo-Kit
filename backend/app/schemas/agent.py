from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.audit import AuditFocus, VerificationItem
from app.schemas.relation import RelationConfig


class AgentStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"


class AgentStep(BaseModel):
    id: str
    name: str
    status: AgentStepStatus
    durationMs: int
    inputSummary: str
    outputSummary: str
    tool: str
    success: bool
    errorMessage: str | None = None


class AuditGenerateRequest(BaseModel):
    task_id: str
    relations: list[RelationConfig] = Field(default_factory=list)


class AuditGenerateResponse(BaseModel):
    auditFocuses: list[AuditFocus]
    verificationItems: list[VerificationItem]
    agentSteps: list[AgentStep]
