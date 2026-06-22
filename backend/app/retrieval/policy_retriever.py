from __future__ import annotations

from app.redis_store.clause_store import ClauseStore


class PolicyRetriever:
    def __init__(self, clause_store: ClauseStore) -> None:
        self.clause_store = clause_store

    def search(self, query: str, today: int, top_k: int = 5) -> list[dict]:
        clauses = self.clause_store.search_text(query, doc_type="policy", top_k=top_k, today=today)
        return [clause.model_dump() for clause in clauses]
