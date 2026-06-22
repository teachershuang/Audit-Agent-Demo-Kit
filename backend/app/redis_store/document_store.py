from __future__ import annotations

import json
from typing import Any

from redis import Redis

from app.schemas.document import DocumentRecord


class DocumentStore:
    def __init__(self, client: Redis) -> None:
        self.client = client

    def save(self, record: DocumentRecord) -> DocumentRecord:
        payload = record.model_dump_json()
        try:
            self.client.execute_command("JSON.SET", f"doc:{record.id}", "$", payload)
        except Exception:
            self.client.set(f"doc:{record.id}", payload)
        return record

    def get(self, doc_id: str) -> DocumentRecord | None:
        try:
            payload = self.client.execute_command("JSON.GET", f"doc:{doc_id}")
        except Exception:
            payload = self.client.get(f"doc:{doc_id}")
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return DocumentRecord.model_validate(json.loads(payload))

    def list(self) -> list[DocumentRecord]:
        items: list[DocumentRecord] = []
        for key in self.client.scan_iter(match="doc:*"):
            try:
                payload = self.client.execute_command("JSON.GET", key)
            except Exception:
                payload = self.client.get(key)
            if not payload:
                continue
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            items.append(DocumentRecord.model_validate(json.loads(payload)))
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def update_fields(self, doc_id: str, **fields: Any) -> DocumentRecord | None:
        record = self.get(doc_id)
        if record is None:
            return None
        updated = record.model_copy(update=fields)
        return self.save(updated)
