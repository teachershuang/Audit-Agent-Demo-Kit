from __future__ import annotations

from typing import Any

from app.services.qwen_service import QwenService
from app.tools.base_tool import BaseTool


class QwenLlmTool(BaseTool):
    name = "qwen_llm_tool"

    def __init__(self, qwen_service: QwenService) -> None:
        self.qwen_service = qwen_service

    async def run(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]):
        return await self.qwen_service.chat_json(system_prompt, user_prompt, schema)
