from __future__ import annotations

from dataclasses import dataclass

from app.agents.audit_focus_agent import AuditFocusAgent
from app.agents.planner import Planner
from app.agents.verification_agent import VerificationAgent
from app.mock.sample_result import build_mock_agent_steps, build_mock_clauses, build_mock_result, build_mock_sections
from app.schemas.agent import AgentStep
from app.schemas.audit import AuditFocus, VerificationItem
from app.schemas.contract import ContractAnalysisResult, TaskStatus
from app.schemas.relation import RelationConfig
from app.services.confidence_service import ConfidenceService
from app.services.document_service import DocumentPreparation, DocumentService
from app.services.evidence_service import EvidenceService
from app.services.ocr_service import OCRService


@dataclass
class ContractAgentArtifacts:
    result: ContractAnalysisResult
    audit_focuses: list[AuditFocus]
    verification_items: list[VerificationItem]
    agent_steps: list[AgentStep]


class ContractAgent:
    def __init__(
        self,
        document_service: DocumentService,
        ocr_service: OCRService,
        audit_focus_agent: AuditFocusAgent,
        verification_agent: VerificationAgent,
        evidence_service: EvidenceService,
        confidence_service: ConfidenceService,
        planner: Planner,
    ) -> None:
        self.document_service = document_service
        self.ocr_service = ocr_service
        self.audit_focus_agent = audit_focus_agent
        self.verification_agent = verification_agent
        self.evidence_service = evidence_service
        self.confidence_service = confidence_service
        self.planner = planner

    async def analyze(
        self,
        task_id: str,
        file_name: str,
        model_name: str,
        relations: list[RelationConfig],
        use_sample: bool,
        file_path=None,
    ) -> ContractAgentArtifacts:
        preparation = self.document_service.prepare(file_name=file_name, file_path=file_path, use_sample=use_sample)
        _plan = self.planner.build_plan(preparation)
        pages = self.ocr_service.extract_pages()
        result = build_mock_result(task_id=task_id, file_name=file_name, model_name=model_name)
        result.pages = pages
        result.sections = build_mock_sections()
        result.clauses = build_mock_clauses()

        audit_focuses = await self.audit_focus_agent.generate(
            sections=result.sections,
            clauses=result.clauses,
            relations=relations,
        )
        verification_items = self.verification_agent.verify(
            sections=result.sections,
            clauses=result.clauses,
            audit_focuses=audit_focuses,
        )

        result.task.confidenceOverview = self.confidence_service.summarize(
            sections=result.sections,
            clauses=result.clauses,
            audit_focuses=audit_focuses,
        )
        result.task.status = TaskStatus.NEEDS_REVIEW
        self.evidence_service.build_index(result)
        agent_steps = build_mock_agent_steps(file_name)
        return ContractAgentArtifacts(
            result=result,
            audit_focuses=audit_focuses,
            verification_items=verification_items,
            agent_steps=agent_steps,
        )
