from __future__ import annotations


class KnowledgeGraphAdapter:
    def query(self, _: dict) -> dict:
        return {
            "status": "not_connected",
            "message": "知识图谱尚未接入，当前仅预留接口。",
        }
