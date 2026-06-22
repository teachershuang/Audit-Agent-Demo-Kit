from __future__ import annotations

import json

from redis import Redis

from app.schemas.rule import RuleRecord


class RuleStore:
    def __init__(self, client: Redis) -> None:
        self.client = client

    def save(self, rule: RuleRecord) -> RuleRecord:
        payload = rule.model_dump_json()
        try:
            self.client.execute_command("JSON.SET", f"rule:{rule.id}", "$", payload)
        except Exception:
            self.client.set(f"rule:{rule.id}", payload)
        if rule.source_document_id:
            self.client.sadd(f"rule_idx:source_document:{rule.source_document_id}", rule.id)
        return rule

    def get(self, rule_id: str) -> RuleRecord | None:
        try:
            payload = self.client.execute_command("JSON.GET", f"rule:{rule_id}")
        except Exception:
            payload = self.client.get(f"rule:{rule_id}")
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return RuleRecord.model_validate(json.loads(payload))

    def list(self) -> list[RuleRecord]:
        items: list[RuleRecord] = []
        for key in self.client.scan_iter(match="rule:*"):
            try:
                payload = self.client.execute_command("JSON.GET", key)
            except Exception:
                payload = self.client.get(key)
            if not payload:
                continue
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            items.append(RuleRecord.model_validate(json.loads(payload)))
        items.sort(key=lambda item: item.id)
        return items

    def list_by_source_document(self, document_id: str) -> list[RuleRecord]:
        rule_ids = self.client.smembers(f"rule_idx:source_document:{document_id}")
        if not rule_ids:
            return [item for item in self.list() if item.source_document_id == document_id]
        items: list[RuleRecord] = []
        for raw_id in rule_ids:
            rule_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
            item = self.get(rule_id)
            if item is not None:
                items.append(item)
        items.sort(key=lambda item: item.id)
        return items

    def delete(self, rule_id: str) -> bool:
        return bool(self.client.delete(f"rule:{rule_id}"))
