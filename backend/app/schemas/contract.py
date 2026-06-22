from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING_UPLOAD = "pending_upload"
    PROCESSING = "processing"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


class EvidenceRef(BaseModel):
    id: str
    page: int
    bbox: tuple[int, int, int, int]
    text: str
    sourceType: str
    sourceId: str
    segmentIndex: int = 0
    segmentCount: int = 1
    isPrimary: bool = True
    accent: str = "cyan"


class DocumentBlock(BaseModel):
    id: str
    text: str
    x: int
    y: int
    width: int
    height: int = 24
    emphasis: bool = False


class ContractPage(BaseModel):
    page: int
    title: str
    width: int
    height: int
    imageUrl: str | None = None
    imageLocalPath: str | None = None
    blocks: list[DocumentBlock] = Field(default_factory=list)
    evidences: list[EvidenceRef] = Field(default_factory=list)


class ContractSection(BaseModel):
    id: str
    title: str
    level: int
    page: int
    summary: str
    confidence: float
    sortOrder: int = 0
    sectionCode: str | None = None
    sectionPath: str | None = None
    blockIds: list[str] = Field(default_factory=list)
    evidenceId: str | None = None


class ClauseTag(BaseModel):
    id: str
    label: str
    coreLabel: str = "其他重要条款"
    labelSource: str = "core"
    title: str
    summary: str
    rawText: str
    page: int
    confidence: float
    sortOrder: int = 0
    sectionTitle: str | None = None
    references: list[str] = Field(default_factory=list)
    structuredFields: dict[str, Any] = Field(default_factory=dict)
    anchorText: str | None = None
    blockIds: list[str] = Field(default_factory=list)
    evidenceId: str
    needHumanReview: bool = False
    discoveryReason: str | None = None
    relatedAuditFocusIds: list[str] = Field(default_factory=list)


class KeyFact(BaseModel):
    id: str
    label: str
    value: str
    page: int
    confidence: float
    evidenceId: str | None = None
    notes: str | None = None


class ConfidenceOverview(BaseModel):
    overall: float
    sections: float
    clauses: float
    audit: float
    warnings: int


class KnowledgeBaseReviewStep(BaseModel):
    id: str
    label: str
    status: str = "pending"
    detail: str | None = None


class KnowledgeBaseReviewState(BaseModel):
    status: str = "idle"
    progressPercent: int = 0
    currentStepId: str | None = None
    currentStepLabel: str | None = None
    message: str | None = None
    detectedCategory: str | None = None
    matchedTemplateId: str | None = None
    matchedTemplateName: str | None = None
    issueCount: int | None = None
    steps: list[KnowledgeBaseReviewStep] = Field(default_factory=list)


class ContractTask(BaseModel):
    taskId: str
    fileName: str
    status: TaskStatus
    createdAt: str
    modelName: str
    confidenceOverview: ConfidenceOverview
    progressPercent: int = 0
    currentStage: str | None = None
    stageDetail: str | None = None
    elapsedMs: int = 0
    knowledgeBaseReview: KnowledgeBaseReviewState | None = None


class ContractAnalysisResult(BaseModel):
    task: ContractTask
    pages: list[ContractPage] = Field(default_factory=list)
    sections: list[ContractSection] = Field(default_factory=list)
    clauses: list[ClauseTag] = Field(default_factory=list)
    keyFacts: list[KeyFact] = Field(default_factory=list)


class UploadResponse(BaseModel):
    task_id: str
