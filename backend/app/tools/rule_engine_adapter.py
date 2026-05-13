from __future__ import annotations


class RuleEngineAdapter:
    def check(self, _: dict) -> dict:
        return {
            "status": "not_connected",
            "message": "规则引擎尚未接入，当前仅预留接口。",
        }
