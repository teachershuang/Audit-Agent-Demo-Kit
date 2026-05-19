from __future__ import annotations

from app.schemas.relation import AuditConfigItem, RelationConfig
from app.storage.local_store import LocalStore


class RelationConfigService:
    def __init__(self, store: LocalStore) -> None:
        self.store = store

    def list(self) -> list[RelationConfig]:
        return self.store.list_relations()

    def list_configs(self) -> list[AuditConfigItem]:
        return [AuditConfigItem.model_validate(item.model_dump()) for item in self.store.list_relations()]

    def create(self, relation: RelationConfig) -> RelationConfig:
        return self.store.upsert_relation(relation)

    def create_config(self, config: AuditConfigItem) -> AuditConfigItem:
        saved = self.store.upsert_relation(RelationConfig.model_validate(config.model_dump()))
        return AuditConfigItem.model_validate(saved.model_dump())

    def update(self, relation_id: str, relation: RelationConfig) -> RelationConfig:
        relation.id = relation_id
        return self.store.upsert_relation(relation)

    def update_config(self, config_id: str, config: AuditConfigItem) -> AuditConfigItem:
        config.id = config_id
        saved = self.store.upsert_relation(RelationConfig.model_validate(config.model_dump()))
        return AuditConfigItem.model_validate(saved.model_dump())

    def delete(self, relation_id: str) -> None:
        self.store.delete_relation(relation_id)
