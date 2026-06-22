from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

import httpx

from app.config import Settings


class ModelProbeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def probe_all(self) -> dict:
        return {
            "text": await self._probe_openai_compatible(
                base_url=self.settings.qwen_base_url,
                api_key=self.settings.qwen_api_key,
                model=self.settings.qwen_model_name,
                capability="text",
            ),
            "vision": await self._probe_openai_compatible(
                base_url=self.settings.qwen_base_url,
                api_key=self.settings.qwen_api_key,
                model=self.settings.qwen_vision_model_name,
                capability="vision",
            ),
            "review_llm": await self._probe_openai_compatible(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
                model=self.settings.llm_model,
                capability="review_llm",
            ),
            "embedding": await self._probe_openai_compatible(
                base_url=self.settings.embedding_base_url,
                api_key=self.settings.embedding_api_key,
                model=self.settings.embedding_model,
                capability="embedding",
            ),
        }

    async def _probe_openai_compatible(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        capability: str,
    ) -> dict:
        checked_at = datetime.now().isoformat(timespec="seconds")
        provider_host = urlparse(base_url).netloc if base_url else None

        if not base_url or not model:
            return {
                "capability": capability,
                "configured_model": model or None,
                "resolved_model": None,
                "provider_host": provider_host,
                "available": False,
                "probe_status": "not_configured",
                "probe_method": "none",
                "checked_at": checked_at,
                "error": "base_url or model is missing",
            }

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
                response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
            model_ids = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
            exact_match = model in model_ids
            return {
                "capability": capability,
                "configured_model": model,
                "resolved_model": model if exact_match else model,
                "provider_host": provider_host,
                "available": exact_match,
                "probe_status": "ok" if exact_match else "model_not_listed",
                "probe_method": "models_endpoint",
                "checked_at": checked_at,
                "available_models_count": len(model_ids),
                "error": None if exact_match else "configured model was not returned by /models",
            }
        except Exception as exc:
            return {
                "capability": capability,
                "configured_model": model,
                "resolved_model": model,
                "provider_host": provider_host,
                "available": False,
                "probe_status": "probe_failed",
                "probe_method": "models_endpoint",
                "checked_at": checked_at,
                "error": str(exc),
            }
