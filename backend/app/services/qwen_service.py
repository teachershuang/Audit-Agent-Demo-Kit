from __future__ import annotations

import json
import re
from typing import Any

import httpx
from jsonschema import ValidationError, validate

from app.config import Settings


class QwenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_mock(self) -> bool:
        return self.settings.use_mock_model or not self.settings.qwen_api_key

    async def chat_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if self.is_mock:
            raise RuntimeError("QwenService is running in mock mode.")

        payload = {
            "model": self.settings.qwen_model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.qwen_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        repaired = self._repair_json(content)
        try:
            validate(instance=repaired, schema=schema)
        except ValidationError as exc:
            raise RuntimeError(f"Qwen JSON schema validation failed: {exc.message}") from exc
        return repaired

    def _repair_json(self, raw_text: str) -> dict[str, Any]:
        candidate = raw_text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?", "", candidate).strip()
            candidate = re.sub(r"```$", "", candidate).strip()
        if not candidate.startswith("{"):
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start >= 0 and end > start:
                candidate = candidate[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Unable to repair model JSON: {exc.msg}") from exc
