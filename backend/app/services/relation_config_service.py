from __future__ import annotations

from app.schemas.relation import RelationConfig
from app.storage.local_store import LocalStore


class RelationConfigService:
    def __init__(self, store: LocalStore) -> None:
        self.store = store

    def list(self) -> list[RelationConfig]:
        return self.store.list_relations()

    def create(self, relation: RelationConfig) -> RelationConfig:
        return self.store.upsert_relation(relation)

    def update(self, relation_id: str, relation: RelationConfig) -> RelationConfig:
        relation.id = relation_id
        return self.store.upsert_relation(relation)

    def delete(self, relation_id: str) -> None:
        self.store.delete_relation(relation_id)
