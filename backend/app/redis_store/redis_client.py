from __future__ import annotations

from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.config import Settings


class ResilientRedisProxy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Redis | None = None

    def _build_client(self) -> Redis:
        return Redis.from_url(
            self.settings.redis_url,
            decode_responses=False,
            socket_keepalive=True,
            health_check_interval=30,
            socket_connect_timeout=5,
            socket_timeout=20,
            retry_on_timeout=True,
        )

    def _get_client(self) -> Redis:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _reset_client(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None

    def _invoke(self, name: str, *args: Any, **kwargs: Any):
        last_error: Exception | None = None
        for _ in range(2):
            client = self._get_client()
            try:
                return getattr(client, name)(*args, **kwargs)
            except (RedisError, OSError) as exc:
                last_error = exc
                self._reset_client()
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Redis call failed: {name}")

    def __getattr__(self, name: str):
        attr = getattr(self._get_client(), name)
        if callable(attr):
            return lambda *args, **kwargs: self._invoke(name, *args, **kwargs)
        return attr


class RedisClientFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: ResilientRedisProxy | None = None

    def get_client(self) -> ResilientRedisProxy:
        if self._client is None:
            self._client = ResilientRedisProxy(self.settings)
        return self._client
