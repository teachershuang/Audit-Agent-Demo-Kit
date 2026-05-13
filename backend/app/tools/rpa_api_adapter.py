from __future__ import annotations


class RpaApiAdapter:
    def fetch(self, _: dict) -> dict:
        return {
            "status": "not_connected",
            "message": "RPA/API 查询能力尚未接入，当前仅预留接口。",
        }
