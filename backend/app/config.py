from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    app_name: str = "Contract Audit Agent"
    app_env: str = "development"
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
    qwen_cache_enabled: bool = True
    qwen_cache_namespace: str = "qwen_v2_multistage"
    scanned_ocr_strategy: str = "vl_primary"
    enable_paddle_ocr: bool = True
    enable_vl_ocr_enhancement: bool = True
    paddle_python_executable: str = "C:/Users/26423/.conda/envs/paddle_test/python.exe"
    paddle_ocr_timeout_seconds: int = 240
    paddle_ocr_batch_size: int = 3
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

    storage_dir: str = "uploads"
    ocr_cache_enabled: bool = True
    ocr_cache_namespace: str = "ocr_v3_vl_semantic"

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
