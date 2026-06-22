from __future__ import annotations

import hashlib
from typing import Iterable

import httpx
import numpy as np

from app.config import Settings


class EmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.max_input_chars = 1800

    async def embed_text(self, text: str) -> list[float]:
        cleaned = text.strip()
        if not cleaned:
            return [0.0] * self.settings.redis_vector_dim
        # Large template clauses can exceed provider-side limits; truncate for stable MVP ingestion.
        cleaned = cleaned[: self.max_input_chars]
        if self.settings.embedding_base_url and self.settings.embedding_model:
            payload = {"model": self.settings.embedding_model, "input": cleaned}
            headers = {"Content-Type": "application/json"}
            if self.settings.embedding_api_key:
                headers["Authorization"] = f"Bearer {self.settings.embedding_api_key}"
            async with httpx.AsyncClient(timeout=self.settings.embedding_timeout_seconds, trust_env=False) as client:
                response = await client.post(
                    f"{self.settings.embedding_base_url.rstrip('/')}/embeddings",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            vector = data.get("data", [{}])[0].get("embedding", [])
            if isinstance(vector, list) and vector:
                return self._normalize_vector([float(item) for item in vector])
        return self._normalize_vector(self._fallback_embedding(cleaned))

    async def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]

    def encode_vector(self, vector: list[float]) -> bytes:
        array = np.array(self._normalize_vector(vector), dtype=np.float32)
        return array.tobytes()

    def _fallback_embedding(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < self.settings.redis_vector_dim:
            for byte in digest:
                values.append((byte / 255.0) * 2 - 1)
                if len(values) >= self.settings.redis_vector_dim:
                    break
            digest = hashlib.sha256(digest).digest()
        return values

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        if len(vector) >= self.settings.redis_vector_dim:
            return vector[: self.settings.redis_vector_dim]
        return vector + [0.0] * (self.settings.redis_vector_dim - len(vector))
