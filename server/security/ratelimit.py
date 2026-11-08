"""Per-domain rate limit (TZ SEC-14: 1-2 requests per second to one site).

GCRA (a token bucket kept as one timestamp). On the server the state is in Redis, so every
worker process shares one limit per domain; in dev and tests it lives in memory.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Protocol

from django.conf import settings

# KEYS[1] = bucket key; ARGV = now (ms), interval (ms), burst. Returns the wait in ms.
_GCRA_LUA = """
local tat = tonumber(redis.call('GET', KEYS[1]) or ARGV[1])
local now = tonumber(ARGV[1])
local interval = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])
if tat < now then tat = now end
local allow_at = tat - interval * (burst - 1)
if now < allow_at then return allow_at - now end
redis.call('SET', KEYS[1], tat + interval, 'PX', interval * burst + 1000)
return 0
"""


class RateLimiter(Protocol):
    def try_acquire(self, key: str) -> float: ...


class MemoryRateLimiter:
    """GCRA in process memory: ``try_acquire`` returns 0 or the seconds to wait."""

    def __init__(self, rate_per_s: float, burst: int = 1) -> None:
        self.interval = 1.0 / rate_per_s
        self.burst = max(1, burst)
        self._tat: dict[str, float] = {}
        self._lock = threading.Lock()

    def try_acquire(self, key: str, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        with self._lock:
            tat = max(self._tat.get(key, now), now)
            allow_at = tat - self.interval * (self.burst - 1)
            if now < allow_at:
                return allow_at - now
            self._tat[key] = tat + self.interval
            return 0.0


class RedisRateLimiter:
    def __init__(self, client: Any, rate_per_s: float, burst: int = 1) -> None:
        self.client = client
        self.interval_ms = int(1000 / rate_per_s)
        self.burst = max(1, burst)
        self._script = client.register_script(_GCRA_LUA)

    def try_acquire(self, key: str) -> float:
        now_ms = int(time.time() * 1000)
        wait_ms = int(self._script(keys=[f"rl:{key}"], args=[now_ms, self.interval_ms, self.burst]))
        return wait_ms / 1000.0


_default: RateLimiter | None = None


def default_limiter() -> RateLimiter:
    global _default
    if _default is None:
        rate = float(settings.YORIQNOMA_REQUESTS_PER_SECOND)
        url = str(settings.YORIQNOMA_RATELIMIT_REDIS_URL)
        if url:
            import redis

            _default = RedisRateLimiter(redis.Redis.from_url(url), rate, burst=2)
        else:
            _default = MemoryRateLimiter(rate, burst=2)
    return _default


async def wait_turn(host: str, limiter: RateLimiter | None = None) -> None:
    limiter = limiter or default_limiter()
    while True:
        delay = limiter.try_acquire(host.lower())
        if delay <= 0:
            return
        await asyncio.sleep(min(delay, 5.0))


def wait_turn_sync(host: str, limiter: RateLimiter | None = None) -> None:
    limiter = limiter or default_limiter()
    while True:
        delay = limiter.try_acquire(host.lower())
        if delay <= 0:
            return
        time.sleep(min(delay, 5.0))
