from __future__ import annotations

from app.redis_store.clause_store import ClauseStore


class HybridRetriever:
    def __init__(self, clause_store: ClauseStore) -> None:
        self.clause_store = clause_store

    async def search(self, query: str, today: int, top_k: int = 5) -> list[dict]:
        text_hits = self.clause_store.search_text(query, doc_type="policy", top_k=top_k, today=today)
        vector_hits = await self.clause_store.vector_search(query, top_k=top_k, today=today)
        merged: dict[str, dict] = {}
        for rank, clause in enumerate(text_hits):
            merged[clause.id] = {"score": float(top_k - rank), "clause": clause.model_dump()}
        for item in vector_hits:
            clause = item["clause"]
            bucket = merged.setdefault(clause["id"], {"score": 0.0, "clause": clause})
            bucket["score"] += float(item["score"])
        return sorted(merged.values(), key=lambda entry: entry["score"], reverse=True)[:top_k]
