from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.config import Settings
from app.services.model_probe_service import ModelProbeService
from app.services.paddle_ocr_service import PaddleOCRService
from app.services.qwen_service import QwenService


@dataclass
class RuntimeModelProfile:
    id: str
    label: str
    description: str
    qwen_api_key: str
    qwen_base_url: str
    qwen_model_name: str
    qwen_vision_model_name: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    scanned_ocr_strategy: str
    enable_vl_ocr_enhancement: bool
    enable_paddle_ocr: bool
    paddle_service_mode: str
    paddle_remote_base_url: str
    paddle_remote_endpoint: str
    paddle_remote_health_path: str
    qwen_parallel_requests: int


class RuntimeModelProfileService:
    def __init__(
        self,
        settings: Settings,
        qwen_service: QwenService,
        paddle_ocr_service: PaddleOCRService,
        model_probe_service: ModelProbeService,
    ) -> None:
        self.settings = settings
        self.qwen_service = qwen_service
        self.paddle_ocr_service = paddle_ocr_service
        self.model_probe_service = model_probe_service
        self.profiles = self._build_profiles()
        self.active_profile_id = (
            settings.runtime_model_profile_default
            if settings.runtime_model_profile_default in self.profiles
            else "public"
        )

    def _build_profiles(self) -> dict[str, RuntimeModelProfile]:
        public_profile = RuntimeModelProfile(
            id="public",
            label="公网模型",
            description="DeepSeek V4 Flash + Qwen VL，适合标准演示和扫描件解析。",
            qwen_api_key=self.settings.qwen_api_key,
            qwen_base_url=self.settings.qwen_base_url,
            qwen_model_name=self.settings.qwen_model_name,
            qwen_vision_model_name=self.settings.qwen_vision_model_name,
            llm_api_key=self.settings.llm_api_key,
            llm_base_url=self.settings.llm_base_url,
            llm_model=self.settings.llm_model,
            embedding_api_key=self.settings.embedding_api_key,
            embedding_base_url=self.settings.embedding_base_url,
            embedding_model=self.settings.embedding_model,
            scanned_ocr_strategy=self.settings.scanned_ocr_strategy,
            enable_vl_ocr_enhancement=self.settings.enable_vl_ocr_enhancement,
            enable_paddle_ocr=self.settings.enable_paddle_ocr,
            paddle_service_mode=self.settings.paddle_service_mode,
            paddle_remote_base_url=self.settings.paddle_remote_base_url,
            paddle_remote_endpoint=self.settings.paddle_remote_endpoint,
            paddle_remote_health_path=self.settings.paddle_remote_health_path,
            qwen_parallel_requests=self.settings.qwen_parallel_requests,
        )
        internal_profile = RuntimeModelProfile(
            id="internal",
            label="内网模型",
            description="Qwen3.6-35B-A3B-GGUF + 内网 Paddle，适合受限网络环境。",
            qwen_api_key=self.settings.internal_qwen_api_key,
            qwen_base_url=self.settings.internal_qwen_base_url,
            qwen_model_name=self.settings.internal_qwen_model_name,
            qwen_vision_model_name=self.settings.internal_qwen_vision_model_name,
            llm_api_key=self.settings.internal_llm_api_key or self.settings.internal_qwen_api_key,
            llm_base_url=self.settings.internal_llm_base_url or self.settings.internal_qwen_base_url,
            llm_model=self.settings.internal_llm_model or self.settings.internal_qwen_model_name,
            embedding_api_key=self.settings.internal_embedding_api_key or self.settings.embedding_api_key,
            embedding_base_url=self.settings.internal_embedding_base_url or self.settings.embedding_base_url,
            embedding_model=self.settings.internal_embedding_model or self.settings.embedding_model,
            scanned_ocr_strategy=self.settings.internal_scanned_ocr_strategy,
            enable_vl_ocr_enhancement=self.settings.internal_enable_vl_ocr_enhancement,
            enable_paddle_ocr=True,
            paddle_service_mode=self.settings.internal_paddle_service_mode,
            paddle_remote_base_url=self.settings.internal_paddle_remote_base_url,
            paddle_remote_endpoint=self.settings.internal_paddle_remote_endpoint,
            paddle_remote_health_path=self.settings.internal_paddle_remote_health_path,
            qwen_parallel_requests=self.settings.internal_qwen_parallel_requests,
        )
        return {public_profile.id: public_profile, internal_profile.id: internal_profile}

    async def initialize(self) -> dict[str, Any]:
        return await self.apply_profile(self.active_profile_id)

    async def apply_profile(self, profile_id: str) -> dict[str, Any]:
        if profile_id not in self.profiles:
            raise ValueError(f"Unknown runtime model profile: {profile_id}")

        profile = self.profiles[profile_id]
        self.settings.qwen_api_key = profile.qwen_api_key
        self.settings.qwen_base_url = profile.qwen_base_url
        self.settings.qwen_model_name = profile.qwen_model_name
        self.settings.qwen_vision_model_name = profile.qwen_vision_model_name
        self.settings.llm_api_key = profile.llm_api_key
        self.settings.llm_base_url = profile.llm_base_url
        self.settings.llm_model = profile.llm_model
        self.settings.embedding_api_key = profile.embedding_api_key
        self.settings.embedding_base_url = profile.embedding_base_url
        self.settings.embedding_model = profile.embedding_model
        self.settings.scanned_ocr_strategy = profile.scanned_ocr_strategy
        self.settings.enable_vl_ocr_enhancement = profile.enable_vl_ocr_enhancement
        self.settings.enable_paddle_ocr = profile.enable_paddle_ocr
        self.settings.qwen_parallel_requests = profile.qwen_parallel_requests
        self.settings.paddle_service_mode = profile.paddle_service_mode
        self.settings.paddle_remote_base_url = profile.paddle_remote_base_url
        self.settings.paddle_remote_endpoint = profile.paddle_remote_endpoint
        self.settings.paddle_remote_health_path = profile.paddle_remote_health_path

        self.qwen_service.refresh_runtime()
        self.paddle_ocr_service.configure(
            mode=profile.paddle_service_mode,
            remote_base_url=profile.paddle_remote_base_url,
            remote_endpoint=profile.paddle_remote_endpoint,
            remote_health_path=profile.paddle_remote_health_path,
        )

        self.active_profile_id = profile_id
        return await self.model_probe_service.probe_all()

    async def get_status(self, runtime_models: dict[str, Any] | None = None) -> dict[str, Any]:
        current_profile = self.profiles[self.active_profile_id]
        runtime_models = runtime_models or await self.model_probe_service.probe_all()
        paddle_probe = await self.paddle_ocr_service.probe_health()
        return {
            "currentProfileId": current_profile.id,
            "currentProfileLabel": current_profile.label,
            "profiles": [
                {
                    "id": profile.id,
                    "label": profile.label,
                    "description": profile.description,
                    "textModel": profile.qwen_model_name,
                    "visionModel": profile.qwen_vision_model_name or None,
                    "reviewModel": profile.llm_model,
                    "ocrStrategy": profile.scanned_ocr_strategy,
                    "paddleMode": profile.paddle_service_mode,
                    "paddleRemoteBaseUrl": profile.paddle_remote_base_url or None,
                }
                for profile in self.profiles.values()
            ],
            "runtimeModels": runtime_models,
            "paddleProbe": paddle_probe,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_profile_id": self.active_profile_id,
            "profiles": {key: asdict(profile) for key, profile in self.profiles.items()},
        }
