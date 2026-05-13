from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.logging_utils import frontend_logger, json_dumps


class FrontendLogPayload(BaseModel):
    level: str = Field(default="info")
    event: str
    message: str | None = None
    context: dict | None = None


def get_logs_router():
    router = APIRouter(prefix="/api/logs", tags=["logs"])

    @router.post("/frontend")
    async def write_frontend_log(payload: FrontendLogPayload):
        frontend_logger.info(
            json_dumps(
                {
                    "level": payload.level,
                    "event": payload.event,
                    "message": payload.message,
                    "context": payload.context or {},
                }
            )
        )
        return {"ok": True}

    return router
