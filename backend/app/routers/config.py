from __future__ import annotations

from fastapi import APIRouter

from app.schemas.relation import AuditConfigItem, RelationConfig
from app.services.relation_config_service import RelationConfigService


def get_config_router(relation_config_service: RelationConfigService):
    router = APIRouter(prefix="/api/config", tags=["config"])

    @router.get("/relations", response_model=list[RelationConfig])
    async def get_relations():
        return relation_config_service.list()

    @router.get("/audit-configs", response_model=list[AuditConfigItem])
    async def get_audit_configs():
        return relation_config_service.list_configs()

    @router.post("/relations", response_model=RelationConfig)
    async def create_relation(relation: RelationConfig):
        return relation_config_service.create(relation)

    @router.post("/audit-configs", response_model=AuditConfigItem)
    async def create_audit_config(config: AuditConfigItem):
        return relation_config_service.create_config(config)

    @router.put("/relations/{relation_id}", response_model=RelationConfig)
    async def update_relation(relation_id: str, relation: RelationConfig):
        return relation_config_service.update(relation_id, relation)

    @router.put("/audit-configs/{config_id}", response_model=AuditConfigItem)
    async def update_audit_config(config_id: str, config: AuditConfigItem):
        return relation_config_service.update_config(config_id, config)

    @router.delete("/relations/{relation_id}")
    async def delete_relation(relation_id: str):
        relation_config_service.delete(relation_id)
        return {"deleted": relation_id}

    @router.delete("/audit-configs/{config_id}")
    async def delete_audit_config(config_id: str):
        relation_config_service.delete(config_id)
        return {"deleted": config_id}

    return router
