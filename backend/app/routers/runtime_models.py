from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.runtime_model_profile_service import RuntimeModelProfileService


class SwitchRuntimeModelProfilePayload(BaseModel):
    profile_id: str


def get_runtime_models_router(runtime_model_profile_service: RuntimeModelProfileService):
    router = APIRouter(prefix="/api/runtime/model-profiles", tags=["runtime-models"])

    @router.get("")
    async def get_runtime_model_profiles(request: Request):
        runtime_models = getattr(request.app.state, "runtime_models", {}) or {}
        return await runtime_model_profile_service.get_status(runtime_models=runtime_models)

    @router.post("/switch")
    async def switch_runtime_model_profile(payload: SwitchRuntimeModelProfilePayload, request: Request):
        try:
            runtime_models = await runtime_model_profile_service.apply_profile(payload.profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.runtime_models = runtime_models
        return await runtime_model_profile_service.get_status(runtime_models=runtime_models)

    return router
