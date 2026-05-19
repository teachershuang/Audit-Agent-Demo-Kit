from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RelationToolSource(str, Enum):
    MODEL_INFERENCE = "model_inference"
    RULE_ENGINE_FUTURE = "rule_engine_future"
    KNOWLEDGE_GRAPH_FUTURE = "knowledge_graph_future"
    ENTERPRISE_RELATION_FUTURE = "enterprise_relation_future"
    INTERNAL_MASTER_DATA_FUTURE = "internal_master_data_future"
    RPA_API_FUTURE = "rpa_api_future"


class RelationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuditConfigType(str, Enum):
    RELATION_FOCUS = "relation_focus"
    RULE_CHECK = "rule_check"
    EXTERNAL_CHECK = "external_check"


class AuditConfigItem(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool = True
    riskPrompt: str
    toolSource: list[RelationToolSource] = Field(default_factory=list)
    priority: RelationPriority = RelationPriority.MEDIUM
    configType: AuditConfigType = AuditConfigType.RELATION_FOCUS
    rulePayload: dict[str, Any] | None = None


class RelationConfig(AuditConfigItem):
    pass
