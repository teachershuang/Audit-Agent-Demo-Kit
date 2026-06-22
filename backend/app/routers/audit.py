from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.logging_utils import app_logger, json_dumps
from app.schemas.agent import AuditGenerateRequest, AuditGenerateResponse
from app.schemas.review import ReviewRequest
from app.storage.local_store import LocalStore


def get_audit_router(store: LocalStore, agent, review_pipeline=None, review_bridge=None):
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
        audit_focuses = artifacts.audit_focuses
        verification_items = artifacts.verification_items
        agent_steps = artifacts.agent_steps
        if review_pipeline is not None and review_bridge is not None:
            try:
                review_result = await review_pipeline.review_contract(ReviewRequest(source_task_id=payload.task_id))
                kb_report = review_result["report"]
                audit_focuses = review_bridge.merge_focuses(audit_focuses, review_bridge.build_focuses(kb_report))
                verification_items = review_bridge.merge_verification_items(
                    verification_items,
                    review_bridge.build_verification_items(kb_report),
                )
                agent_steps = list(agent_steps)
                agent_steps.append(review_bridge.build_agent_step(kb_report))
            except Exception as exc:
                app_logger.warning(
                    json_dumps(
                        {
                            "event": "knowledge_base_review_regenerate_merge_failed",
                            "taskId": payload.task_id,
                            "error": str(exc),
                        }
                    )
                )
        store.save_result(
            task_id=payload.task_id,
            result=artifacts.result,
            audit_focuses=audit_focuses,
            verification_items=verification_items,
            agent_steps=agent_steps,
        )
        return AuditGenerateResponse(
            auditFocuses=audit_focuses,
            verificationItems=verification_items,
            agentSteps=agent_steps,
        )

    return router
