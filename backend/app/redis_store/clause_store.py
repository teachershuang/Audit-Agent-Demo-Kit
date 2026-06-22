from __future__ import annotations

import math
from typing import Any

import numpy as np
from redis import Redis

from app.embedding.embedding_client import EmbeddingClient
from app.schemas.clause import ClauseRecord


class ClauseStore:
    def __init__(self, client: Redis, embedding_client: EmbeddingClient) -> None:
        self.client = client
        self.embedding_client = embedding_client

    def save_many(self, clauses: list[ClauseRecord]) -> None:
        pipeline = self.client.pipeline(transaction=False)
        for clause in clauses:
            clause_key = f"clause:{clause.id}"
            mapping = {
                "id": clause.id,
                "document_id": clause.document_id,
                "doc_type": clause.doc_type,
                "template_id": clause.template_id or "",
                "template_name": clause.template_name or "",
                "category_lv1": clause.category_lv1 or "",
                "category_lv2": clause.category_lv2 or "",
                "clause_no": clause.clause_no or "",
                "title": clause.title,
                "clause_type": clause.clause_type,
                "content": clause.content,
                "page_start": clause.page_start,
                "page_end": clause.page_end,
                "status": clause.status,
                "effective_ts": clause.effective_ts,
                "abolish_ts": clause.abolish_ts,
                "risk_tags": ",".join(clause.risk_tags),
                "embedding": self.embedding_client.encode_vector(clause.embedding),
            }
            pipeline.hset(clause_key, mapping=mapping)
            pipeline.sadd(f"clause_idx:document:{clause.document_id}", clause.id)
            pipeline.sadd(f"clause_idx:doctype:{clause.doc_type}", clause.id)
            if clause.template_id:
                pipeline.sadd(f"clause_idx:template:{clause.template_id}", clause.id)
        pipeline.execute()

    def get(self, clause_id: str) -> ClauseRecord | None:
        payload = self.client.hgetall(f"clause:{clause_id}")
        if not payload:
            return None
        return self._hydrate(payload)

    def list(
        self,
        *,
        document_id: str | None = None,
        template_id: str | None = None,
        doc_type: str | None = None,
        include_embedding: bool = False,
    ) -> list[ClauseRecord]:
        items: list[ClauseRecord] = []
        if document_id:
            keys = [f"clause:{item.decode('utf-8') if isinstance(item, bytes) else item}" for item in self.client.smembers(f"clause_idx:document:{document_id}")]
        elif template_id:
            keys = [f"clause:{item.decode('utf-8') if isinstance(item, bytes) else item}" for item in self.client.smembers(f"clause_idx:template:{template_id}")]
        elif doc_type:
            keys = [f"clause:{item.decode('utf-8') if isinstance(item, bytes) else item}" for item in self.client.smembers(f"clause_idx:doctype:{doc_type}")]
        else:
            keys = list(self.client.scan_iter(match="clause:*"))

        if not keys and (document_id or template_id or doc_type):
            return self._list_with_scan_fallback(
                document_id=document_id,
                template_id=template_id,
                doc_type=doc_type,
                include_embedding=include_embedding,
            )

        for key in keys:
            payload = self.client.hgetall(key)
            if not payload:
                continue
            clause = self._hydrate(payload, include_embedding=include_embedding)
            if document_id and clause.document_id != document_id:
                continue
            if template_id and clause.template_id != template_id:
                continue
            if doc_type and clause.doc_type != doc_type:
                continue
            items.append(clause)
        items.sort(key=lambda item: (item.template_id or "", item.page_start, item.clause_no or ""))
        return items

    def _list_with_scan_fallback(
        self,
        *,
        document_id: str | None,
        template_id: str | None,
        doc_type: str | None,
        include_embedding: bool,
    ) -> list[ClauseRecord]:
        items: list[ClauseRecord] = []
        pipeline = self.client.pipeline(transaction=False)
        for key in self.client.scan_iter(match="clause:*"):
            payload = self.client.hgetall(key)
            if not payload:
                continue
            clause = self._hydrate(payload, include_embedding=include_embedding)
            if document_id and clause.document_id != document_id:
                continue
            if template_id and clause.template_id != template_id:
                continue
            if doc_type and clause.doc_type != doc_type:
                continue
            items.append(clause)
            pipeline.sadd(f"clause_idx:document:{clause.document_id}", clause.id)
            pipeline.sadd(f"clause_idx:doctype:{clause.doc_type}", clause.id)
            if clause.template_id:
                pipeline.sadd(f"clause_idx:template:{clause.template_id}", clause.id)
        pipeline.execute()
        items.sort(key=lambda item: (item.template_id or "", item.page_start, item.clause_no or ""))
        return items

    def update_document_status(self, document_id: str, *, status: str, abolish_ts: int | None = None) -> None:
        pipeline = self.client.pipeline(transaction=False)
        for clause in self.list(document_id=document_id):
            mapping = {
                "status": status,
                "abolish_ts": abolish_ts if abolish_ts is not None else clause.abolish_ts,
            }
            pipeline.hset(f"clause:{clause.id}", mapping=mapping)
        pipeline.execute()

    def search_text(
        self,
        query: str,
        *,
        doc_type: str | None = None,
        category_lv1: str | None = None,
        category_lv2: str | None = None,
        template_id: str | None = None,
        top_k: int = 10,
        today: int | None = None,
    ) -> list[ClauseRecord]:
        terms = [item for item in query.strip().split() if item]
        scored: list[tuple[float, ClauseRecord]] = []
        for clause in self.list(doc_type=doc_type, include_embedding=False):
            if today is not None and not self._is_effective(clause, today):
                continue
            if category_lv1 and clause.category_lv1 != category_lv1:
                continue
            if category_lv2 and clause.category_lv2 != category_lv2:
                continue
            if template_id and clause.template_id != template_id:
                continue
            haystack = f"{clause.title}\n{clause.content}"
            score = 0.0
            for term in terms:
                if term in haystack:
                    score += 1.0
            if score > 0:
                scored.append((score, clause))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    async def vector_search(self, query: str, top_k: int = 10, today: int | None = None) -> list[dict[str, Any]]:
        vector = await self.embedding_client.embed_text(query)
        query_array = np.array(vector, dtype=np.float32)
        scored: list[dict[str, Any]] = []
        for clause in self.list(include_embedding=True):
            if today is not None and not self._is_effective(clause, today):
                continue
            clause_array = np.array(clause.embedding, dtype=np.float32)
            denom = float(np.linalg.norm(query_array) * np.linalg.norm(clause_array))
            similarity = 0.0 if denom == 0 else float(np.dot(query_array, clause_array) / denom)
            scored.append({"score": similarity, "clause": clause.model_dump()})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def template_candidates(self, *, detected_category: str, keywords: list[str], today: int) -> list[dict[str, Any]]:
        aggregate: dict[str, dict[str, Any]] = {}
        for clause in self.list(doc_type="template", include_embedding=False):
            if not clause.template_id or not self._is_effective(clause, today):
                continue
            score = 0.0
            if detected_category and (detected_category in (clause.category_lv1 or "") or detected_category in (clause.category_lv2 or "")):
                score += 3.0
            for keyword in keywords:
                if keyword and (keyword in clause.title or keyword in clause.content):
                    score += 1.0
            if score <= 0:
                continue
            bucket = aggregate.setdefault(
                clause.template_id,
                {
                    "template_id": clause.template_id,
                    "template_name": clause.template_name,
                    "category_lv1": clause.category_lv1,
                    "category_lv2": clause.category_lv2,
                    "score": 0.0,
                },
            )
            bucket["score"] += score
        return sorted(aggregate.values(), key=lambda item: item["score"], reverse=True)

    @staticmethod
    def _is_effective(clause: ClauseRecord, today: int) -> bool:
        return clause.status in {"effective", "partially_effective"} and clause.effective_ts <= today <= clause.abolish_ts

    def _hydrate(self, payload: dict[bytes, bytes], *, include_embedding: bool = False) -> ClauseRecord:
        embedding_bytes = payload.get(b"embedding", b"")
        vector = np.frombuffer(embedding_bytes, dtype=np.float32).tolist() if include_embedding and embedding_bytes else []
        return ClauseRecord(
            id=payload[b"id"].decode("utf-8"),
            document_id=payload[b"document_id"].decode("utf-8"),
            doc_type=payload[b"doc_type"].decode("utf-8"),
            template_id=payload[b"template_id"].decode("utf-8") or None,
            template_name=payload[b"template_name"].decode("utf-8") or None,
            category_lv1=payload[b"category_lv1"].decode("utf-8") or None,
            category_lv2=payload[b"category_lv2"].decode("utf-8") or None,
            clause_no=payload[b"clause_no"].decode("utf-8") or None,
            title=payload[b"title"].decode("utf-8"),
            clause_type=payload[b"clause_type"].decode("utf-8"),
            content=payload[b"content"].decode("utf-8"),
            page_start=int(payload[b"page_start"].decode("utf-8")),
            page_end=int(payload[b"page_end"].decode("utf-8")),
            status=payload[b"status"].decode("utf-8"),
            effective_ts=int(payload[b"effective_ts"].decode("utf-8")),
            abolish_ts=int(payload[b"abolish_ts"].decode("utf-8")),
            risk_tags=[item for item in payload[b"risk_tags"].decode("utf-8").split(",") if item],
            embedding=vector,
        )
