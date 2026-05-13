from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import Settings, get_settings
from app.schemas.contract import ContractAnalysisResult, UploadResponse
from app.storage.local_store import LocalStore


def get_contract_router(store: LocalStore, agent):
    router = APIRouter(prefix="/api/contracts", tags=["contracts"])

    @router.post("/upload", response_model=UploadResponse)
    async def upload_contract(
        file: UploadFile | None = File(default=None),
        use_sample: bool = Form(default=False),
        settings: Settings = Depends(get_settings),
    ) -> UploadResponse:
        file_name = file.filename if file else "sample_contract.pdf"
        upload_dir = Path(__file__).resolve().parents[2] / settings.storage_dir
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = None
        if file:
            task_file_name = f"{file_name}"
            file_path = upload_dir / task_file_name
            file_path.write_bytes(await file.read())

        record = store.create_task(
            file_name=file_name,
            model_name="Qwen / Mock Hybrid" if settings.use_mock_model or not settings.qwen_api_key else settings.qwen_model_name,
            use_sample=use_sample or file is None,
            file_path=file_path,
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

        artifacts = await agent.analyze(
            task_id=record.task.taskId,
            file_name=record.task.fileName,
            model_name=record.task.modelName,
            relations=store.list_relations(),
            use_sample=record.use_sample,
            file_path=record.file_path,
        )
        store.save_result(
            task_id=task_id,
            result=artifacts.result,
            audit_focuses=artifacts.audit_focuses,
            verification_items=artifacts.verification_items,
            agent_steps=artifacts.agent_steps,
        )
        return {"task_id": task_id, "status": artifacts.result.task.status}

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
