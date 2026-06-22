from __future__ import annotations

import json
from datetime import datetime

from redis import Redis

from app.schemas.review import ReviewTaskRecord


class ReviewTaskStore:
    def __init__(self, client: Redis) -> None:
        self.client = client

    def save(self, task: ReviewTaskRecord) -> ReviewTaskRecord:
        payload = task.model_dump_json()
        key = f"review_task:{task.task_id}"
        try:
            self.client.execute_command("JSON.SET", key, "$", payload)
        except Exception:
            self.client.set(key, payload)
        return task

    def get(self, task_id: str) -> ReviewTaskRecord | None:
        key = f"review_task:{task_id}"
        try:
            payload = self.client.execute_command("JSON.GET", key)
        except Exception:
            payload = self.client.get(key)
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return ReviewTaskRecord.model_validate(json.loads(payload))

    def update(self, task_id: str, **changes) -> ReviewTaskRecord | None:
        task = self.get(task_id)
        if task is None:
            return None
        updated = task.model_copy(
            update={
                **changes,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return self.save(updated)
