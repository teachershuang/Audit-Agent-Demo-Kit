from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


def get_run_logs_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / ".run-logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_file_logger(name: str, file_name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    log_path = get_run_logs_dir() / file_name
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


app_logger = configure_file_logger("contract_agent.app", "backend.app.log")
frontend_logger = configure_file_logger("contract_agent.frontend", "frontend.app.log")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
