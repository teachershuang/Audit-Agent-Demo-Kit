from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from app.redis_store.clause_store import ClauseStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.policy_retriever import PolicyRetriever
from app.schemas.clause import ClauseSearchRequest


def _today_ts() -> int:
    return int(datetime.now().strftime("%Y%m%d"))


def get_base_debug_router(
    *,
    clause_store: ClauseStore,
    policy_retriever: PolicyRetriever,
    hybrid_retriever: HybridRetriever,
):
    router = APIRouter(prefix="/api/base/debug", tags=["base-debug"])

    @router.post("/search-policy")
    async def search_policy(payload: ClauseSearchRequest):
        return policy_retriever.search(payload.query, today=_today_ts(), top_k=payload.top_k)

    @router.post("/search-template")
    async def search_template(payload: ClauseSearchRequest):
        clauses = clause_store.search_text(
            payload.query,
            doc_type="template",
            category_lv1=payload.category_lv1,
            category_lv2=payload.category_lv2,
            template_id=payload.template_id,
            top_k=payload.top_k,
            today=_today_ts(),
        )
        return [item.model_dump() for item in clauses]

    @router.post("/vector-search")
    async def vector_search(payload: ClauseSearchRequest):
        return await clause_store.vector_search(payload.query, top_k=payload.top_k, today=_today_ts())

    return router
