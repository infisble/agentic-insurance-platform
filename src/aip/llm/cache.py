"""L2 exact-match response cache (ADR 0005).

The key covers everything that can change the answer: task, prompt version, model, effort
and the *masked* input. Values are masked outputs, re-identified with the current case's
mapping on read, so a hit never carries another person's data.
"""

import hashlib
import json
import time
from typing import Any, Protocol


def cache_key(**parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return "aip:llm:" + hashlib.sha256(raw.encode()).hexdigest()


class ResponseCache(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def set(self, key: str, value: dict[str, Any], ttl_s: int) -> None: ...


class MemoryCache:
    """Process-local cache for development and tests."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._data.get(key)
        if item is None or item[0] < time.monotonic():
            return None
        return item[1]

    async def set(self, key: str, value: dict[str, Any], ttl_s: int) -> None:
        self._data[key] = (time.monotonic() + ttl_s, value)


class RedisCache:
    """Redis/Valkey/Azure Managed Redis. Optional dependency: pip install '.[redis]'."""

    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self._redis = Redis.from_url(url)

    async def get(self, key: str) -> dict[str, Any] | None:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: dict[str, Any], ttl_s: int) -> None:
        await self._redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_s)
