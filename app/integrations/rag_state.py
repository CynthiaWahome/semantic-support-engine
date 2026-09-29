"""Cache and rate-limit state adapters for the RAG service."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Protocol

_INCREMENT_WITH_EXPIRY_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RagStateStore(Protocol):
    """Minimal state boundary required by RAG safeguards."""

    def get(self, key: str) -> str | None:
        """Return a value or ``None`` when it is absent or expired."""
        ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store a value for the requested number of seconds."""
        ...

    def increment(self, key: str, ttl_seconds: int) -> int:
        """Increment a counter and apply its expiry on first creation."""
        ...


class UpstashRagStateStore:
    """Adapt an injected Upstash Redis client to the RAG state boundary."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def get(self, key: str) -> str | None:
        """Read one cache or rate-limit value."""
        value = self.client.get(key)
        return None if value is None else str(value)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Write one value with an explicit expiry."""
        self.client.set(key, value, ex=ttl_seconds)

    def increment(self, key: str, ttl_seconds: int) -> int:
        """Increment a counter and expire it when first created."""
        return int(
            self.client.eval(
                _INCREMENT_WITH_EXPIRY_SCRIPT,
                [key],
                [str(ttl_seconds)],
            )
        )


class InMemoryRagStateStore:
    """Thread-safe TTL state store for tests and single-process development."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float]] = {}
        self._counts: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        """Return an unexpired value."""
        now = time.monotonic()
        with self._lock:
            value = self._values.get(key)
            if value is None or value[1] <= now:
                self._values.pop(key, None)
                return None
            return value[0]

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store a value with a monotonic expiry."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._values[key] = (value, time.monotonic() + ttl_seconds)

    def increment(self, key: str, ttl_seconds: int) -> int:
        """Increment a counter while preserving its original window expiry."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = time.monotonic()
        with self._lock:
            current = self._counts.get(key)
            if current is None or current[1] <= now:
                count = 1
                expires_at = now + ttl_seconds
            else:
                count = current[0] + 1
                expires_at = current[1]
            self._counts[key] = (count, expires_at)
            return count
