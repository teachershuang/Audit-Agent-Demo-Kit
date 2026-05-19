from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.agents.audit_focus_agent import AuditFocusAgent
from app.agents.contract_parser_agent import ContractParserAgent
from app.agents.planner import Planner
from app.agents.verification_agent import VerificationAgent
from app.schemas.agent import AgentStep, AgentStepStatus
from app.schemas.audit import AuditFocus, VerificationItem
from app.schemas.contract import ContractAnalysisResult, ContractTask, TaskStatus
from app.schemas.relation import RelationConfig
from app.services.confidence_service import ConfidenceService
from app.services.document_service import DocumentService
from app.services.evidence_service import EvidenceService
from app.services.ocr_service import OCRService
from app.tools.rule_engine_adapter import RuleEngineAdapter


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
        parser_agent: ContractParserAgent,
        audit_focus_agent: AuditFocusAgent,
        verification_agent: VerificationAgent,
        evidence_service: EvidenceService,
        confidence_service: ConfidenceService,
        planner: Planner,
        storage_dir: Path,
        rule_engine_adapter: RuleEngineAdapter,
    ) -> None:
        self.document_service = document_service
        self.ocr_service = ocr_service
        self.parser_agent = parser_agent
        self.audit_focus_agent = audit_focus_agent
        self.verification_agent = verification_agent
        self.evidence_service = evidence_service
        self.confidence_service = confidence_service
        self.planner = planner
        self.storage_dir = storage_dir
        self.rule_engine_adapter = rule_engine_adapter

    async def analyze(
        self,
        task: ContractTask,
        relations: list[RelationConfig],
        use_builtin_example: bool,
        file_path: Path | None = None,
        progress_callback: Callable[[int, str, str], None] | None = None,
    ) -> ContractAgentArtifacts:
        preparation = self.document_service.prepare(
            file_name=task.fileName,
            file_path=file_path,
            use_builtin_example=use_builtin_example,
        )
        plan = self.planner.build_plan(preparation)
        self._emit_progress(progress_callback, 6, "document_prepared", f"已准备 {preparation.file_type} 文档，开始进入解析流程。")

        agent_steps: list[AgentStep] = [
            self._step("step_001", "接收上传文件", AgentStepStatus.SUCCESS, 60, task.fileName, f"任务 {task.taskId}", "upload_handler"),
            self._step(
                "step_002",
                "识别文件类型",
                AgentStepStatus.SUCCESS,
                48,
                preparation.file_name,
                f"{preparation.file_type} / {preparation.recommended_pipeline}",
                "document_service",
            ),
        ]

        extracted = await self.ocr_service.extract_document(
            task_id=task.taskId,
            preparation=preparation,
            output_root=self.storage_dir,
            progress_callback=progress_callback,
        )
        agent_steps.append(
            self._step(
                "step_003",
                "文档预处理与文本抽取",
                AgentStepStatus.WARNING if extracted.warnings else AgentStepStatus.SUCCESS,
                360,
                ", ".join(plan[:4]),
                (
                    f"{len(extracted.pages)} 页，链路 {extracted.pipeline}"
                    if not extracted.warnings
                    else f"{len(extracted.pages)} 页，链路 {extracted.pipeline}，有 {len(extracted.warnings)} 页需要人工复核"
                ),
                "document_service + ocr_service",
            )
        )

        self._emit_progress(progress_callback, 60, "section_reconstruction", "正在根据 OCR blocks 重建合同章节结构。")
        sections = await self.parser_agent.reconstruct_sections(extracted.pages)
        self._emit_progress(progress_callback, 72, "section_reconstruction", f"已识别 {len(sections)} 个章节。")

        self._emit_progress(progress_callback, 76, "clause_tagging", "正在识别关键条款。")
        clauses = await self.parser_agent.identify_clauses(extracted.pages, sections, relations)
        self._emit_progress(progress_callback, 82, "clause_tagging", f"已识别 {len(clauses)} 条关键条款。")

        agent_steps.append(
            self._step(
                "step_004",
                "章节结构识别",
                AgentStepStatus.SUCCESS,
                720,
                f"{len(extracted.pages)} pages",
                f"Identified {len(sections)} sections",
                "qwen_service",
            )
        )
        agent_steps.append(
            self._step(
                "step_005",
                "条款标签识别",
                AgentStepStatus.SUCCESS,
                980,
                f"{len(sections)} sections",
                f"Identified {len(clauses)} clauses",
                "qwen_service",
            )
        )

        key_facts = await self.parser_agent.extract_key_facts(extracted.pages, clauses)
        self._emit_progress(progress_callback, 88, "fact_extraction", f"已抽取 {len(key_facts)} 项关键信息。")
        agent_steps.append(
            self._step(
                "step_006",
                "关键信息抽取",
                AgentStepStatus.SUCCESS,
                680,
                f"{len(clauses)} clauses",
                f"Extracted {len(key_facts)} key facts",
                "qwen_service",
            )
        )

        self._emit_progress(progress_callback, 90, "evidence_and_audit", "正在并行执行证据 grounding、规则校验和审计关注点生成。")
        evidence_task = self.evidence_service.attach_evidences(extracted.pages, sections, clauses, key_facts)
        rule_task = self.rule_engine_adapter.evaluate(
            task_id=task.taskId,
            sections=sections,
            clauses=clauses,
            key_facts=key_facts,
            configs=relations,
        )
        audit_task = self.audit_focus_agent.generate(
            sections=sections,
            clauses=clauses,
            relations=relations,
            key_facts=key_facts,
        )
        _, rule_results, audit_focuses = await asyncio.gather(evidence_task, rule_task, audit_task)
        self._emit_progress(progress_callback, 96, "audit_focus_generation", f"已生成 {len(audit_focuses)} 项审计关注方向，并完成证据 grounding。")

        agent_steps.append(
            self._step(
                "step_007",
                "证据 grounding",
                AgentStepStatus.SUCCESS,
                210,
                "sections / clauses / key facts",
                f"Mapped {sum(len(page.evidences) for page in extracted.pages)} evidence references",
                "evidence_service",
            )
        )
        self._bind_clause_audit_links(clauses, audit_focuses)
        agent_steps.append(
            self._step(
                "step_008",
                "规则引擎校验",
                AgentStepStatus.SUCCESS if rule_results.get("status") in {"ok", "no_rule_configs", "not_connected"} else AgentStepStatus.WARNING,
                260,
                f"{len(relations)} audit configs",
                f"Rule engine status: {rule_results.get('status', 'unknown')} / matches {len(rule_results.get('matchedRules', []))}",
                "gorules_adapter",
            )
        )
        agent_steps.append(
            self._step(
                "step_009",
                "审计关注点生成",
                AgentStepStatus.SUCCESS,
                840,
                f"{len(relations)} audit configs",
                f"Generated {len(audit_focuses)} audit focus items",
                "audit_focus_agent",
            )
        )

        verification_items = await self.verification_agent.verify(
            sections=sections,
            clauses=clauses,
            audit_focuses=audit_focuses,
            rule_results=rule_results,
        )
        self._emit_progress(progress_callback, 98, "verification", f"已整理 {len(verification_items)} 条校验与证据链说明。")
        agent_steps.append(
            self._step(
                "step_010",
                "异构校验",
                AgentStepStatus.SUCCESS,
                180,
                f"{len(clauses)} clauses / {len(audit_focuses)} audit items",
                f"Built {len(verification_items)} verification records",
                "verification_agent",
            )
        )

        task.confidenceOverview = self.confidence_service.summarize(
            sections=sections,
            clauses=clauses,
            audit_focuses=audit_focuses,
        )
        task.status = (
            TaskStatus.NEEDS_REVIEW
            if extracted.warnings or any(item.needHumanReview for item in clauses)
            else TaskStatus.COMPLETED
        )

        result = ContractAnalysisResult(
            task=task,
            pages=extracted.pages,
            sections=sections,
            clauses=clauses,
            keyFacts=key_facts,
        )
        return ContractAgentArtifacts(
            result=result,
            audit_focuses=audit_focuses,
            verification_items=verification_items,
            agent_steps=agent_steps,
        )

    @staticmethod
    def _emit_progress(
        progress_callback: Callable[[int, str, str], None] | None,
        progress_percent: int,
        current_stage: str,
        stage_detail: str,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(progress_percent, current_stage, stage_detail)

    @staticmethod
    def _bind_clause_audit_links(clauses: list, audit_focuses: list[AuditFocus]) -> None:
        mapping: dict[str, list[str]] = {}
        for item in audit_focuses:
            for clause_id in item.evidenceClauseIds:
                mapping.setdefault(clause_id, []).append(item.id)
        for clause in clauses:
            clause.relatedAuditFocusIds = mapping.get(clause.id, [])

    @staticmethod
    def _step(
        step_id: str,
        name: str,
        status: AgentStepStatus,
        duration_ms: int,
        input_summary: str,
        output_summary: str,
        tool: str,
    ) -> AgentStep:
        return AgentStep(
            id=step_id,
            name=name,
            status=status,
            durationMs=duration_ms,
            inputSummary=input_summary,
            outputSummary=output_summary,
            tool=tool,
            success=status in {AgentStepStatus.SUCCESS, AgentStepStatus.WARNING},
            errorMessage=None,
        )
