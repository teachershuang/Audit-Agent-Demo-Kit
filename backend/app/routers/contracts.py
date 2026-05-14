from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.logging_utils import app_logger, json_dumps
from app.schemas.contract import ContractAnalysisResult, UploadResponse
from app.schemas.contract import TaskStatus
from app.storage.local_store import LocalStore


def get_contract_router(store: LocalStore, agent):
    router = APIRouter(prefix="/api/contracts", tags=["contracts"])

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
            stage_detail="Analysis task started.",
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
                store.save_result(
                    task_id=task_id,
                    result=artifacts.result,
                    audit_focuses=artifacts.audit_focuses,
                    verification_items=artifacts.verification_items,
                    agent_steps=artifacts.agent_steps,
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

        record.analysis_job = asyncio.create_task(run_analysis())
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
