from __future__ import annotations

from typing import Any

from app.schemas.relation import AuditConfigItem, RelationConfig


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
            "configType": relation.configType.value,
            "rulePayload": relation.rulePayload,
        }
        for relation in relations
        if relation.enabled
    ]


def build_audit_config_prompt_context(configs: list[AuditConfigItem]) -> list[dict[str, Any]]:
    return build_relation_prompt_context([RelationConfig.model_validate(item.model_dump()) for item in configs])
