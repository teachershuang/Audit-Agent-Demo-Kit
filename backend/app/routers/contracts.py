from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.logging_utils import app_logger, json_dumps
from app.schemas.contract import (
    ContractAnalysisResult,
    KnowledgeBaseReviewState,
    KnowledgeBaseReviewStep,
    TaskStatus,
    UploadResponse,
)
from app.schemas.review import ReviewRequest
from app.storage.local_store import LocalStore


def get_contract_router(store: LocalStore, agent, review_pipeline=None, review_bridge=None):
    router = APIRouter(prefix="/api/contracts", tags=["contracts"])

    def build_kb_review_state(
        *,
        status: str,
        progress_percent: int,
        current_step_id: str | None,
        current_step_label: str | None,
        message: str | None,
        failed: bool = False,
        detail: str | None = None,
    ) -> KnowledgeBaseReviewState:
        steps = [
            KnowledgeBaseReviewStep(id="classify_contract", label="识别合同类型", status="pending"),
            KnowledgeBaseReviewStep(id="match_template", label="匹配有效范本", status="pending"),
            KnowledgeBaseReviewStep(id="extract_schema", label="抽取结构化字段", status="pending"),
            KnowledgeBaseReviewStep(id="compare_template", label="比对范本条款", status="pending"),
            KnowledgeBaseReviewStep(id="retrieve_policy", label="检索制度依据", status="pending"),
            KnowledgeBaseReviewStep(id="run_rules", label="执行规则校验", status="pending"),
            KnowledgeBaseReviewStep(id="generate_issues", label="生成审查问题", status="pending"),
            KnowledgeBaseReviewStep(id="save_report", label="写入审查报告", status="pending"),
        ]
        order = [item.id for item in steps]
        if current_step_id in order:
            current_index = order.index(current_step_id)
            for index, step in enumerate(steps):
                if index < current_index:
                    step.status = "completed"
                elif index == current_index:
                    step.status = "failed" if failed else ("completed" if status == "completed" else "running")
                    step.detail = detail
        elif status == "completed":
            for step in steps:
                step.status = "completed"
        return KnowledgeBaseReviewState(
            status=status,
            progressPercent=progress_percent,
            currentStepId=current_step_id,
            currentStepLabel=current_step_label,
            message=message,
            steps=steps,
        )

    def start_knowledge_base_merge(
        *,
        task_id: str,
        result: ContractAnalysisResult,
        audit_focuses,
        verification_items,
        agent_steps,
        final_task_status: TaskStatus,
    ) -> None:
        if review_pipeline is None or review_bridge is None:
            return

        store.update_task(
            task_id,
            status=final_task_status,
            progress_percent=90,
            current_stage="knowledge_base_review",
            stage_detail="制度底座校验中，可先查看主结果。",
            knowledge_base_review=build_kb_review_state(
                status="running",
                progress_percent=0,
                current_step_id="classify_contract",
                current_step_label="识别合同类型",
                message="制度底座已启动，正在识别合同类型。",
            ),
        )

        async def run_knowledge_base_merge() -> None:
            try:
                review_result = await review_pipeline.review_contract(
                    ReviewRequest(source_task_id=task_id),
                    progress_callback=lambda state: store.update_task(
                        task_id,
                        status=final_task_status,
                        progress_percent=min(99, 90 + round((state.progressPercent or 0) * 0.09)),
                        current_stage="knowledge_base_review",
                        stage_detail=state.message,
                        knowledge_base_review=state,
                    ),
                )
                kb_report = review_result["report"]
                result.task.status = final_task_status
                result.task.knowledgeBaseReview = store.get_task(task_id).task.knowledgeBaseReview
                merged_focuses = review_bridge.merge_focuses(
                    audit_focuses,
                    review_bridge.build_focuses(kb_report),
                )
                merged_verification = review_bridge.merge_verification_items(
                    verification_items,
                    review_bridge.build_verification_items(kb_report),
                )
                merged_steps = list(agent_steps)
                merged_steps.append(review_bridge.build_agent_step(kb_report))
                store.save_result(
                    task_id=task_id,
                    result=result,
                    audit_focuses=merged_focuses,
                    verification_items=merged_verification,
                    agent_steps=merged_steps,
                )
                app_logger.info(
                    json_dumps(
                        {
                            "event": "knowledge_base_review_merged",
                            "taskId": task_id,
                            "kbIssues": len(kb_report.issues),
                            "mergedAuditFocuses": len(merged_focuses),
                            "mergedVerificationItems": len(merged_verification),
                        }
                    )
                )
            except Exception as exc:
                result.task.status = final_task_status
                store.update_task(
                    task_id,
                    status=final_task_status,
                    progress_percent=98,
                    current_stage="knowledge_base_review",
                    stage_detail=f"制度底座校验失败：{exc}",
                    knowledge_base_review=build_kb_review_state(
                        status="failed",
                        progress_percent=100,
                        current_step_id="save_report",
                        current_step_label="制度校验失败",
                        message=f"制度底座校验失败：{exc}",
                        failed=True,
                        detail=str(exc),
                    ),
                )
                result.task.knowledgeBaseReview = store.get_task(task_id).task.knowledgeBaseReview
                app_logger.warning(
                    json_dumps(
                        {
                            "event": "knowledge_base_review_merge_failed",
                            "taskId": task_id,
                            "error": str(exc),
                        }
                    )
                )
                store.save_result(
                    task_id=task_id,
                    result=result,
                    audit_focuses=audit_focuses,
                    verification_items=verification_items,
                    agent_steps=agent_steps,
                )

        threading.Thread(target=lambda: asyncio.run(run_knowledge_base_merge()), daemon=True).start()

    def start_result_reanalysis(task_id: str, updated_result: ContractAnalysisResult) -> None:
        record = store.get_task(task_id)
        store.replace_result(task_id, updated_result)
        store.update_task(
            task_id,
            status=TaskStatus.PROCESSING,
            progress_percent=84,
            current_stage="draft_reanalysis",
            stage_detail="已应用结构化字段修改，正在重新生成审查结果。",
            knowledge_base_review=KnowledgeBaseReviewState(status="idle", progressPercent=0, steps=[]),
        )

        async def run_refresh() -> None:
            try:
                result = updated_result.model_copy(deep=True)
                task = record.task.model_copy(deep=True)
                task.status = TaskStatus.PROCESSING
                result.task = task
                relations = store.list_relations()
                store.update_task(
                    task_id,
                    progress_percent=88,
                    current_stage="draft_reanalysis",
                    stage_detail="正在根据已编辑字段重新执行规则与审查关注点。",
                )
                await agent.evidence_service.attach_evidences(result.pages, result.sections, result.clauses, result.keyFacts)
                rule_task = agent.rule_engine_adapter.evaluate(
                    task_id=task_id,
                    sections=result.sections,
                    clauses=result.clauses,
                    key_facts=result.keyFacts,
                    configs=relations,
                )
                audit_task = agent.audit_focus_agent.generate(
                    sections=result.sections,
                    clauses=result.clauses,
                    relations=relations,
                    key_facts=result.keyFacts,
                )
                rule_results, model_audit_focuses = await asyncio.gather(rule_task, audit_task)
                rule_audit_focuses = agent.audit_focus_agent.build_rule_engine_focuses(
                    clauses=result.clauses,
                    relations=relations,
                    rule_results=rule_results,
                )
                audit_focuses = agent.audit_focus_agent._dedupe_audit_focuses(rule_audit_focuses + model_audit_focuses)
                agent._bind_clause_audit_links(result.clauses, audit_focuses)
                verification_items = await agent.verification_agent.verify(
                    sections=result.sections,
                    clauses=result.clauses,
                    audit_focuses=audit_focuses,
                    rule_results=rule_results,
                )
                result.task.confidenceOverview = agent.confidence_service.summarize(
                    sections=result.sections,
                    clauses=result.clauses,
                    audit_focuses=audit_focuses,
                )
                result.task.status = TaskStatus.NEEDS_REVIEW if any(item.needHumanReview for item in result.clauses) else TaskStatus.COMPLETED
                refresh_steps = [
                    agent._step(
                        "step_edit_001",
                        "应用结构化字段修改",
                        "success",
                        120,
                        f"{len(result.clauses)} clauses / {len(result.keyFacts)} key facts",
                        "已将页面编辑同步到任务草稿",
                        "result_editor",
                    ),
                    agent._step(
                        "step_edit_002",
                        "重新生成审查关注点",
                        "success",
                        420,
                        f"{len(result.clauses)} clauses",
                        f"生成 {len(audit_focuses)} 项审查关注点",
                        "audit_focus_agent",
                    ),
                    agent._step(
                        "step_edit_003",
                        "重新生成校验证据",
                        "success",
                        180,
                        f"{len(audit_focuses)} audit items",
                        f"形成 {len(verification_items)} 条校验记录",
                        "verification_agent",
                    ),
                ]
                store.save_result(
                    task_id=task_id,
                    result=result,
                    audit_focuses=audit_focuses,
                    verification_items=verification_items,
                    agent_steps=refresh_steps,
                )
                start_knowledge_base_merge(
                    task_id=task_id,
                    result=result,
                    audit_focuses=audit_focuses,
                    verification_items=verification_items,
                    agent_steps=refresh_steps,
                    final_task_status=result.task.status,
                )
                app_logger.info(
                    json_dumps(
                        {
                            "event": "result_reanalysis_completed",
                            "taskId": task_id,
                            "clauses": len(result.clauses),
                            "keyFacts": len(result.keyFacts),
                            "auditFocuses": len(audit_focuses),
                            "verificationItems": len(verification_items),
                        }
                    )
                )
            except Exception as exc:
                store.update_task(
                    task_id,
                    status=TaskStatus.NEEDS_REVIEW,
                    progress_percent=96,
                    current_stage="draft_reanalysis_failed",
                    stage_detail=f"编辑后重审失败：{exc}",
                )
                app_logger.exception(
                    json_dumps(
                        {
                            "event": "result_reanalysis_failed",
                            "taskId": task_id,
                            "error": str(exc),
                        }
                    )
                )

        threading.Thread(target=lambda: asyncio.run(run_refresh()), daemon=True).start()

    @router.post("/upload", response_model=UploadResponse)
    async def upload_contract(
        file: UploadFile | None = File(default=None),
        use_builtin_example: bool = Form(default=False),
        settings: Settings = Depends(get_settings),
    ) -> UploadResponse:
        app_logger.info(
            json_dumps(
                {
                    "event": "upload_contract_received",
                    "fileName": file.filename if file else None,
                    "contentType": file.content_type if file else None,
                    "useBuiltinExample": use_builtin_example or file is None,
                }
            )
        )
        record = store.create_task(
            file_name=file.filename if file else "example_contract.pdf",
            model_name=settings.qwen_model_name,
            use_builtin_example=use_builtin_example or file is None,
            file_path=None,
        )
        task_dir = Path(__file__).resolve().parents[2] / settings.storage_dir / record.task.taskId
        task_dir.mkdir(parents=True, exist_ok=True)
        if file:
            file_path = task_dir / (file.filename or "contract.pdf")
            content = await file.read()
            file_path.write_bytes(content)
            record.file_path = file_path
            app_logger.info(
                json_dumps(
                    {
                        "event": "upload_contract_saved",
                        "taskId": record.task.taskId,
                        "fileName": file.filename,
                        "size": len(content),
                        "targetPath": str(file_path),
                    }
                )
            )
        return UploadResponse(task_id=record.task.taskId)

    @router.get("/{task_id}")
    async def get_contract_task(task_id: str):
        try:
            return store.get_task(task_id).task
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @router.post("/{task_id}/analyze")
    async def analyze_contract(task_id: str):
        try:
            record = store.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

        if record.result and record.task.status != TaskStatus.PROCESSING:
            return {
                "task_id": task_id,
                "status": record.task.status,
                "auditFocuses": [item.model_dump() for item in record.audit_focuses],
                "verificationItems": [item.model_dump() for item in record.verification_items],
                "agentSteps": [item.model_dump() for item in record.agent_steps],
            }

        if record.analysis_job and not record.analysis_job.done():
            return {
                "task_id": task_id,
                "status": record.task.status,
                "auditFocuses": [item.model_dump() for item in record.audit_focuses],
                "verificationItems": [item.model_dump() for item in record.verification_items],
                "agentSteps": [item.model_dump() for item in record.agent_steps],
            }

        app_logger.info(
            json_dumps(
                {
                    "event": "analyze_contract_started",
                    "taskId": task_id,
                    "fileName": record.task.fileName,
                    "useBuiltinExample": record.use_builtin_example,
                    "filePath": str(record.file_path) if record.file_path else None,
                }
            )
        )
        store.update_task(
            task_id,
            status=TaskStatus.PROCESSING,
            progress_percent=8,
            current_stage="analysis_started",
            stage_detail="分析任务已启动，正在准备文档和执行链路。",
        )

        def progress_callback(progress_percent: int, current_stage: str, stage_detail: str) -> None:
            store.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress_percent=progress_percent,
                current_stage=current_stage,
                stage_detail=stage_detail,
            )

        async def run_analysis() -> None:
            try:
                artifacts = await agent.analyze(
                    task=record.task,
                    relations=store.list_relations(),
                    use_builtin_example=record.use_builtin_example,
                    file_path=record.file_path,
                    progress_callback=progress_callback,
                )
                app_logger.info(
                    json_dumps(
                        {
                            "event": "analyze_contract_completed",
                            "taskId": task_id,
                            "status": artifacts.result.task.status,
                            "pages": len(artifacts.result.pages),
                            "sections": len(artifacts.result.sections),
                            "clauses": len(artifacts.result.clauses),
                            "keyFacts": len(artifacts.result.keyFacts),
                            "auditFocuses": len(artifacts.audit_focuses),
                            "verificationItems": len(artifacts.verification_items),
                        }
                    )
                )
                final_task_status = artifacts.result.task.status
                store.save_result(
                    task_id=task_id,
                    result=artifacts.result,
                    audit_focuses=artifacts.audit_focuses,
                    verification_items=artifacts.verification_items,
                    agent_steps=artifacts.agent_steps,
                )
                start_knowledge_base_merge(
                    task_id=task_id,
                    result=artifacts.result,
                    audit_focuses=artifacts.audit_focuses,
                    verification_items=artifacts.verification_items,
                    agent_steps=artifacts.agent_steps,
                    final_task_status=final_task_status,
                )
            except Exception as exc:
                store.update_task(
                    task_id,
                    status=TaskStatus.NEEDS_REVIEW,
                    progress_percent=record.task.progressPercent,
                    current_stage="analysis_failed",
                    stage_detail=str(exc),
                )
                app_logger.exception(
                    json_dumps(
                        {
                            "event": "analyze_contract_failed",
                            "taskId": task_id,
                            "error": str(exc),
                        }
                    )
                )
            finally:
                record.analysis_job = None

        loop = asyncio.get_running_loop()
        record.analysis_job = loop.run_in_executor(None, lambda: asyncio.run(run_analysis()))
        return {
            "task_id": task_id,
            "status": store.get_task(task_id).task.status,
            "auditFocuses": [],
            "verificationItems": [],
            "agentSteps": [],
        }

    @router.get("/{task_id}/result", response_model=ContractAnalysisResult)
    async def get_contract_result(task_id: str) -> ContractAnalysisResult:
        try:
            record = store.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if not record.result:
            raise HTTPException(status_code=404, detail="Result not generated")
        return record.result

    @router.post("/{task_id}/reanalyze-from-result")
    async def reanalyze_from_result(task_id: str, payload: ContractAnalysisResult = Body(...)):
        try:
            store.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if payload.task.taskId != task_id:
            raise HTTPException(status_code=400, detail="Task id mismatch")
        app_logger.info(
            json_dumps(
                {
                    "event": "result_reanalysis_requested",
                    "taskId": task_id,
                    "clauses": len(payload.clauses),
                    "keyFacts": len(payload.keyFacts),
                }
            )
        )
        start_result_reanalysis(task_id, payload.model_copy(deep=True))
        return {
            "task_id": task_id,
            "status": store.get_task(task_id).task.status,
            "message": "已接收编辑草稿，正在重新审查并同步制度底座。",
        }

    @router.get("/{task_id}/pages/{page}")
    async def get_contract_page(task_id: str, page: int):
        try:
            record = store.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if not record.result:
            raise HTTPException(status_code=404, detail="Result not generated")
        for item in record.result.pages:
            if item.page == page:
                return item
        raise HTTPException(status_code=404, detail="Page not found")

    @router.get("/{task_id}/pages/{page}/image")
    async def get_contract_page_image(
        task_id: str,
        page: int,
        settings: Settings = Depends(get_settings),
    ):
        image_path = Path(__file__).resolve().parents[2] / settings.storage_dir / task_id / "pages" / f"page_{page:03d}.png"
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Page image not found")
        return FileResponse(image_path)

    @router.get("/{task_id}/evidence/{evidence_id}")
    async def get_contract_evidence(task_id: str, evidence_id: str):
        try:
            record = store.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if not record.result:
            raise HTTPException(status_code=404, detail="Result not generated")
        for page in record.result.pages:
            for evidence in page.evidences:
                if evidence.id == evidence_id:
                    return evidence
        raise HTTPException(status_code=404, detail="Evidence not found")

    return router
