from __future__ import annotations

from fastapi import APIRouter

from app.schemas.relation import RelationConfig
from app.services.relation_config_service import RelationConfigService


def get_config_router(relation_config_service: RelationConfigService):
    router = APIRouter(prefix="/api/config", tags=["config"])

    @router.get("/relations", response_model=list[RelationConfig])
    async def get_relations():
        return relation_config_service.list()

    @router.post("/relations", response_model=RelationConfig)
    async def create_relation(relation: RelationConfig):
        return relation_config_service.create(relation)

    @router.put("/relations/{relation_id}", response_model=RelationConfig)
    async def update_relation(relation_id: str, relation: RelationConfig):
        return relation_config_service.update(relation_id, relation)

    @router.delete("/relations/{relation_id}")
    async def delete_relation(relation_id: str):
        relation_config_service.delete(relation_id)
        return {"deleted": relation_id}

    return router
