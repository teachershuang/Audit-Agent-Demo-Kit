from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.base_support import KnowledgeBaseService
from app.redis_store.rule_store import RuleStore
from app.schemas.rule import RulePatchRequest, RuleRecord


def get_base_rules_router(rule_store: RuleStore, knowledge_base_service: KnowledgeBaseService):
    router = APIRouter(prefix="/api/base/rules", tags=["base-rules"])

    @router.post("")
    async def create_rule(payload: RuleRecord):
        return rule_store.save(payload)

    @router.get("")
    async def list_rules():
        return [item.model_dump() for item in rule_store.list()]

    @router.get("/{rule_id}")
    async def get_rule(rule_id: str):
        rule = rule_store.get(rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        return rule

    @router.get("/{rule_id}/metadata")
    async def get_rule_metadata(rule_id: str):
        payload = knowledge_base_service.rule_metadata(rule_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        return payload

    @router.patch("/{rule_id}")
    async def patch_rule(rule_id: str, payload: RulePatchRequest):
        current = rule_store.get(rule_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        updated = current.model_copy(update=payload.model_dump(exclude_none=True))
        return rule_store.save(updated)

    @router.delete("/{rule_id}")
    async def delete_rule(rule_id: str):
        deleted = rule_store.delete(rule_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"deleted": True}

    return router
