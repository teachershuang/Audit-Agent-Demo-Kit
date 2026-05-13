from __future__ import annotations


class EnterpriseRelationAdapter:
    def lookup(self, _: dict) -> dict:
        return {
            "status": "not_connected",
            "message": "企业关系数据尚未接入，当前仅预留接口。",
        }
