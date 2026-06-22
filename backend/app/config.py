from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    app_name: str = "Contract Audit Agent"
    app_env: str = "development"
    log_level: str = "DEBUG"
    log_max_bytes: int = 8_000_000
    log_backup_count: int = 8
    log_body_max_chars: int = 6000
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    cors_allow_origin_regex: str = (
        r"^https?://("
        r"localhost|"
        r"127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    )

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model_name: str = "qwen-plus"
    qwen_vision_model_name: str = "qwen-vl-plus"
    runtime_model_profile_default: str = "public"
    qwen_cache_enabled: bool = True
    qwen_cache_namespace: str = "qwen_v2_multistage"
    scanned_ocr_strategy: str = "vl_primary"
    enable_paddle_ocr: bool = True
    enable_vl_ocr_enhancement: bool = True
    paddle_service_mode: str = "local_subprocess"
    paddle_python_executable: str = "C:/Users/26423/.conda/envs/paddle_test/python.exe"
    paddle_ocr_timeout_seconds: int = 240
    paddle_ocr_batch_size: int = 3
    paddle_remote_base_url: str = ""
    paddle_remote_endpoint: str = "/ocr"
    paddle_remote_health_path: str = "/health"
    paddle_remote_timeout_seconds: int = 8
    scanned_vl_concurrency: int = 6
    qwen_parallel_requests: int = 10
    section_batch_size: int = 4
    section_batch_overlap: int = 1
    clause_batch_size: int = 4
    key_fact_batch_size: int = 6
    gorules_enabled: bool = False
    gorules_mode: str = "remote_api"
    gorules_base_url: str = ""
    gorules_api_key: str = ""
    gorules_decision_path: str = "/validate"
    gorules_timeout_seconds: int = 30
    gorules_trace_enabled: bool = False
    gorules_local_decision_file: str = "docs/gorules-contract-audit-decision.json"

    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_index_prefix: str = "clause:"
    redis_vector_dim: int = 1536
    redis_vector_distance_metric: str = "COSINE"

    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 60

    internal_qwen_api_key: str = ""
    internal_qwen_base_url: str = ""
    internal_qwen_model_name: str = "Qwen3.6-35B-A3B-GGUF"
    internal_qwen_vision_model_name: str = ""
    internal_llm_api_key: str = ""
    internal_llm_base_url: str = ""
    internal_llm_model: str = "Qwen3.6-35B-A3B-GGUF"
    internal_embedding_api_key: str = ""
    internal_embedding_base_url: str = ""
    internal_embedding_model: str = ""
    internal_paddle_service_mode: str = "remote_first"
    internal_paddle_remote_base_url: str = ""
    internal_paddle_remote_endpoint: str = "/ocr"
    internal_paddle_remote_health_path: str = "/health"
    internal_scanned_ocr_strategy: str = "paddle_primary"
    internal_enable_vl_ocr_enhancement: bool = False
    internal_qwen_parallel_requests: int = 8

    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_timeout_seconds: int = 60

    storage_dir: str = "uploads"
    ocr_cache_enabled: bool = True
    ocr_cache_namespace: str = "ocr_v3_vl_semantic"

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        if not self.qwen_api_key and self.llm_api_key:
            self.qwen_api_key = self.llm_api_key
        if not self.qwen_base_url and self.llm_base_url:
            self.qwen_base_url = self.llm_base_url
        if not self.qwen_model_name and self.llm_model:
            self.qwen_model_name = self.llm_model

        if not self.llm_api_key and self.qwen_api_key:
            self.llm_api_key = self.qwen_api_key
        if not self.llm_base_url and self.qwen_base_url:
            self.llm_base_url = self.qwen_base_url
        if not self.llm_model and self.qwen_model_name:
            self.llm_model = self.qwen_model_name

        if not self.internal_qwen_api_key and self.internal_llm_api_key:
            self.internal_qwen_api_key = self.internal_llm_api_key
        if not self.internal_qwen_base_url and self.internal_llm_base_url:
            self.internal_qwen_base_url = self.internal_llm_base_url
        if not self.internal_qwen_model_name and self.internal_llm_model:
            self.internal_qwen_model_name = self.internal_llm_model

        if not self.internal_llm_api_key and self.internal_qwen_api_key:
            self.internal_llm_api_key = self.internal_qwen_api_key
        if not self.internal_llm_base_url and self.internal_qwen_base_url:
            self.internal_llm_base_url = self.internal_qwen_base_url
        if not self.internal_llm_model and self.internal_qwen_model_name:
            self.internal_llm_model = self.internal_qwen_model_name

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ):
        return init_settings, dotenv_settings, env_settings, file_secret_settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
