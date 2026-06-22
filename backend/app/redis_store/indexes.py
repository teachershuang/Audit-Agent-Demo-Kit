from __future__ import annotations

from redis import Redis

from app.config import Settings


class RedisIndexManager:
    def __init__(self, client: Redis, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def ensure_indexes(self) -> None:
        try:
            existing = self.client.execute_command("FT._LIST")
            if any(item.decode("utf-8") == "idx:clauses" for item in existing):
                return
        except Exception:
            existing = []
        self.client.execute_command(
            "FT.CREATE",
            "idx:clauses",
            "ON",
            "HASH",
            "PREFIX",
            "1",
            self.settings.redis_index_prefix,
            "SCHEMA",
            "content",
            "TEXT",
            "title",
            "TEXT",
            "doc_type",
            "TAG",
            "document_id",
            "TAG",
            "template_id",
            "TAG",
            "category_lv1",
            "TAG",
            "category_lv2",
            "TAG",
            "clause_type",
            "TAG",
            "status",
            "TAG",
            "effective_ts",
            "NUMERIC",
            "abolish_ts",
            "NUMERIC",
            "risk_tags",
            "TAG",
            "embedding",
            "VECTOR",
            "HNSW",
            "6",
            "TYPE",
            "FLOAT32",
            "DIM",
            self.settings.redis_vector_dim,
            "DISTANCE_METRIC",
            self.settings.redis_vector_distance_metric,
        )
