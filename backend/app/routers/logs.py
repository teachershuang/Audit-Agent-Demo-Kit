from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.logging_utils import frontend_logger, get_run_logs_dir, json_dumps


class FrontendLogPayload(BaseModel):
    level: str = Field(default="info")
    event: str
    message: str | None = None
    context: dict | None = None


def get_logs_router():
    router = APIRouter(prefix="/api/logs", tags=["logs"])

    @router.post("/frontend")
    async def write_frontend_log(payload: FrontendLogPayload):
        level_name = str(payload.level or "info").upper()
        frontend_logger.log(
            getattr(logging, level_name, logging.INFO),
            json_dumps(
                {
                    "event": payload.event,
                    "level": payload.level,
                    "message": payload.message,
                    "context": payload.context or {},
                }
            ),
        )
        return {"ok": True}

    @router.get("/file")
    async def read_log_file(path: str = Query(...)):
        logs_dir = get_run_logs_dir().resolve()
        target_path = Path(path).expanduser().resolve()
        try:
            target_path.relative_to(logs_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Log file path is outside .run-logs") from exc
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Log file not found")
        return {
            "path": str(target_path),
            "content": target_path.read_text(encoding="utf-8"),
        }

    return router
