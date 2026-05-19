from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas.relation import RelationConfig
from app.storage.local_store import LocalStore
from app.tools.rule_engine_adapter import RuleEngineAdapter


class RuleEvaluateTaskRequest(BaseModel):
    task_id: str
    relations: list[RelationConfig] | None = None
    trace: bool = False


class RuleEvaluateContextRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    relations: list[RelationConfig] | None = None
    trace: bool = False


def get_rules_router(store: LocalStore, adapter: RuleEngineAdapter):
    router = APIRouter(prefix="/api/rules", tags=["rules"])

    @router.post("/evaluate-task")
    async def evaluate_task_rules(payload: RuleEvaluateTaskRequest):
        try:
            record = store.get_task(payload.task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if not record.result:
            raise HTTPException(status_code=404, detail="Result not generated")

        relations = payload.relations or store.list_relations()
        rule_input = adapter.build_rule_input(
            task_id=payload.task_id,
            sections=record.result.sections,
            clauses=record.result.clauses,
            key_facts=record.result.keyFacts,
            configs=relations,
        )
        return await adapter.evaluate_rule_input(rule_input, relations, trace=payload.trace)

    @router.post("/evaluate-context")
    async def evaluate_context_rules(payload: RuleEvaluateContextRequest):
        relations = payload.relations or store.list_relations()
        return await adapter.evaluate_rule_input(payload.context, relations, trace=payload.trace)

    return router
