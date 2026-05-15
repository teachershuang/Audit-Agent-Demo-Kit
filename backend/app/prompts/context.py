from __future__ import annotations

from typing import Any

from app.schemas.relation import RelationConfig


def build_relation_prompt_context(relations: list[RelationConfig]) -> list[dict[str, Any]]:
    return [
        {
            "id": relation.id,
            "name": relation.name,
            "description": relation.description,
            "enabled": relation.enabled,
            "riskPrompt": relation.riskPrompt,
            "toolSource": [tool.value for tool in relation.toolSource],
            "priority": relation.priority.value,
        }
        for relation in relations
        if relation.enabled
    ]
