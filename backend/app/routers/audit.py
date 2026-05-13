from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.logging_utils import app_logger, json_dumps
from app.schemas.agent import AuditGenerateRequest, AuditGenerateResponse
from app.storage.local_store import LocalStore


def get_audit_router(store: LocalStore, agent):
    router = APIRouter(prefix="/api/audit", tags=["audit"])

    @router.post("/generate", response_model=AuditGenerateResponse)
    async def generate_audit(payload: AuditGenerateRequest):
        try:
            record = store.get_task(payload.task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if not record.result:
            raise HTTPException(status_code=404, detail="Result not generated")
        app_logger.info(
            json_dumps(
                {
                    "event": "audit_regenerate_started",
                    "taskId": payload.task_id,
                    "relationCount": len(payload.relations),
                }
            )
        )

        artifacts = await agent.analyze(
            task=record.task,
            relations=payload.relations,
            use_builtin_example=record.use_builtin_example,
            file_path=record.file_path,
        )
        app_logger.info(
            json_dumps(
                {
                    "event": "audit_regenerate_completed",
                    "taskId": payload.task_id,
                    "auditFocuses": len(artifacts.audit_focuses),
                    "verificationItems": len(artifacts.verification_items),
                }
            )
        )
        store.set_relations(payload.relations)
        store.save_result(
            task_id=payload.task_id,
            result=artifacts.result,
            audit_focuses=artifacts.audit_focuses,
            verification_items=artifacts.verification_items,
            agent_steps=artifacts.agent_steps,
        )
        return AuditGenerateResponse(
            auditFocuses=artifacts.audit_focuses,
            verificationItems=artifacts.verification_items,
            agentSteps=artifacts.agent_steps,
        )

    return router
