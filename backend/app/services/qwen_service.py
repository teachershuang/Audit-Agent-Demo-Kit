from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx
from jsonschema import ValidationError, validate

from app.config import Settings


class QwenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_available(self) -> bool:
        return bool(self.settings.qwen_api_key)

    async def chat_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available:
            raise RuntimeError("Qwen API key is not configured.")

        payload = {
            "model": self.settings.qwen_model_name,
            "messages": [
                {
                    "role": "system",
                    "content": f"{system_prompt}\n必须仅返回合法 JSON 对象。",
                },
                {
                    "role": "user",
                    "content": f"{user_prompt}\n请只输出 JSON。",
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        data = await self._post_chat(payload=payload, timeout=60)
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        repaired = self._repair_json(content)
        self._validate_schema(instance=repaired, schema=schema, label="Qwen JSON")
        return repaired

    async def vision_json(
        self,
        prompt: str,
        image_path: Path,
        schema: dict[str, Any],
        timeout: int = 120,
    ) -> dict[str, Any]:
        if not self.is_available:
            raise RuntimeError("Qwen API key is not configured.")

        image_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        payload = {
            "model": self.settings.qwen_vision_model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{prompt}\n请只输出 JSON。"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        data = await self._post_chat(payload=payload, timeout=timeout)
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        repaired = self._repair_json(content)
        self._validate_schema(instance=repaired, schema=schema, label="Qwen vision JSON")
        return repaired

    async def _post_chat(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.qwen_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if response.is_error:
                    raise RuntimeError(f"Qwen API error {response.status_code}: {response.text}")
        except httpx.ReadTimeout as exc:
            raise RuntimeError(f"Qwen request timed out after {timeout} seconds.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Qwen request failed: {exc}") from exc
        return response.json()

    @staticmethod
    def _validate_schema(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
        try:
            validate(instance=instance, schema=schema)
        except ValidationError as exc:
            raise RuntimeError(f"{label} schema validation failed: {exc.message}") from exc

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
            decoder = json.JSONDecoder()
            for index, char in enumerate(candidate):
                if char != "{":
                    continue
                try:
                    parsed, _ = decoder.raw_decode(candidate[index:])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
            raise RuntimeError(f"Unable to repair model JSON: {exc.msg}") from exc
