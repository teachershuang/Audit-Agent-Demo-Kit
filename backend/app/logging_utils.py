from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


LOG_MAX_CHARS = 6000


def get_run_logs_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / ".run-logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def truncate_for_log(data: Any, max_chars: int = LOG_MAX_CHARS) -> Any:
    if data is None:
        return None
    if isinstance(data, dict):
        return {str(key): truncate_for_log(value, max_chars=max_chars) for key, value in data.items()}
    if isinstance(data, list):
        return [truncate_for_log(value, max_chars=max_chars) for value in data[:80]]
    if isinstance(data, tuple):
        return [truncate_for_log(value, max_chars=max_chars) for value in data[:80]]
    if isinstance(data, (int, float, bool)):
        return data
    text = str(data)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]} ... [truncated {len(text) - max_chars} chars]"


def _as_pretty_lines(value: Any, indent: str = "  ") -> list[str]:
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(truncate_for_log(value), ensure_ascii=False, indent=2, default=str)
        return [f"{indent}{line}" for line in text.splitlines()]
    text = str(truncate_for_log(value))
    return [f"{indent}{line}" for line in text.splitlines()] or [indent]


class PrettyJsonFormatter(logging.Formatter):
    default_time_format = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.default_time_format)
        level = record.levelname.ljust(5)
        base = f"{timestamp} | {level} | {record.name}"
        payload = self._coerce_payload(record)

        if isinstance(payload, dict):
            event = str(payload.get("event") or payload.get("message") or "log")
            lines = [f"{base} | {event}"]
            for key, value in payload.items():
                if key == "event":
                    continue
                value_lines = _as_pretty_lines(value)
                if len(value_lines) == 1 and not value_lines[0].strip().startswith("{") and not value_lines[0].strip().startswith("["):
                    lines.append(f"  {key}: {value_lines[0].strip()}")
                else:
                    lines.append(f"  {key}:")
                    lines.extend([f"    {line.strip()}" for line in value_lines])
        else:
            lines = [f"{base} | {record.getMessage()}"]

        if record.exc_info:
            lines.append(self.formatException(record.exc_info))
        return "\n".join(lines)

    @staticmethod
    def _coerce_payload(record: logging.LogRecord) -> Any:
        raw = record.msg
        if isinstance(raw, dict):
            return raw
        message = record.getMessage()
        try:
            return json.loads(message)
        except Exception:
            return message


def configure_file_logger(name: str, file_name: str, *, level: int = logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    log_path = get_run_logs_dir() / file_name
    handler = RotatingFileHandler(log_path, maxBytes=8_000_000, backupCount=8, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(PrettyJsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


app_logger = configure_file_logger("contract_agent.app", "backend.app.log")
frontend_logger = configure_file_logger("contract_agent.frontend", "frontend.app.log")
