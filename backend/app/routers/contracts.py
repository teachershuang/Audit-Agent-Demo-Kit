from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.schemas.contract import ContractAnalysisResult, UploadResponse
from app.storage.local_store import LocalStore


def get_contract_router(store: LocalStore, agent):
    router = APIRouter(prefix="/api/contracts", tags=["contracts"])

    @router.post("/upload", response_model=UploadResponse)
    async def upload_contract(
        file: UploadFile | None = File(default=None),
        use_builtin_example: bool = Form(default=False),
        settings: Settings = Depends(get_settings),
    ) -> UploadResponse:
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
            file_path.write_bytes(await file.read())
            record.file_path = file_path
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

        artifacts = await agent.analyze(
            task=record.task,
            relations=store.list_relations(),
            use_builtin_example=record.use_builtin_example,
            file_path=record.file_path,
        )
        store.save_result(
            task_id=task_id,
            result=artifacts.result,
            audit_focuses=artifacts.audit_focuses,
            verification_items=artifacts.verification_items,
            agent_steps=artifacts.agent_steps,
        )
        return {
            "task_id": task_id,
            "status": artifacts.result.task.status,
            "auditFocuses": [item.model_dump() for item in artifacts.audit_focuses],
            "verificationItems": [item.model_dump() for item in artifacts.verification_items],
            "agentSteps": [item.model_dump() for item in artifacts.agent_steps],
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
