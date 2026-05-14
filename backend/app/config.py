from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    app_name: str = "合同智能解析与审计关注点 Agent"
    app_env: str = "development"
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    cors_allow_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model_name: str = "qwen-plus"
    qwen_vision_model_name: str = "qwen-vl-plus"
    enable_paddle_ocr: bool = True
    enable_vl_ocr_enhancement: bool = True
    paddle_python_executable: str = "C:/Users/26423/.conda/envs/paddle_test/python.exe"
    paddle_ocr_timeout_seconds: int = 240
    scanned_vl_concurrency: int = 1

    storage_dir: str = "uploads"

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
