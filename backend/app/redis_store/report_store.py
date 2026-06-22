from __future__ import annotations

import json

from redis import Redis

from app.schemas.review import ContractSchema, ReviewReport


class ReportStore:
    def __init__(self, client: Redis) -> None:
        self.client = client

    def save_schema(self, contract_schema: ContractSchema) -> ContractSchema:
        payload = contract_schema.model_dump_json()
        try:
            self.client.execute_command("JSON.SET", f"contract_schema:{contract_schema.contract_id}", "$", payload)
        except Exception:
            self.client.set(f"contract_schema:{contract_schema.contract_id}", payload)
        return contract_schema

    def get_schema(self, contract_id: str) -> ContractSchema | None:
        try:
            payload = self.client.execute_command("JSON.GET", f"contract_schema:{contract_id}")
        except Exception:
            payload = self.client.get(f"contract_schema:{contract_id}")
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return ContractSchema.model_validate(json.loads(payload))

    def save_report(self, report: ReviewReport) -> ReviewReport:
        payload = report.model_dump_json()
        try:
            self.client.execute_command("JSON.SET", f"review_report:{report.contract_id}", "$", payload)
        except Exception:
            self.client.set(f"review_report:{report.contract_id}", payload)
        return report

    def get_report(self, contract_id: str) -> ReviewReport | None:
        try:
            payload = self.client.execute_command("JSON.GET", f"review_report:{contract_id}")
        except Exception:
            payload = self.client.get(f"review_report:{contract_id}")
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return ReviewReport.model_validate(json.loads(payload))
