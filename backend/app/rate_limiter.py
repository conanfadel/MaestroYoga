import os
import threading
import time
from collections import defaultdict, deque
from typing import Protocol
from uuid import uuid4

try:
    import redis
except Exception:  # pragma: no cover - fallback for missing/broken redis package
    redis = None  # type: ignore[assignment]


class RateLimiter(Protocol):
    def allow(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        lockout_seconds: int = 0,
        max_lockout_seconds: int | None = None,
    ) -> bool:
        ...


class InMemoryRateLimiter:
    """Process-local fixed window limiter with optional lockout."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lockouts: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        lockout_seconds: int = 0,
        max_lockout_seconds: int | None = None,
    ) -> bool:
        now = time.time()
        with self._lock:
            locked_until = self._lockouts.get(key, 0)
            if locked_until > now:
                return False

            q = self._events[key]
            while q and (now - q[0]) > window_seconds:
                q.popleft()
            current_count = len(q)
            if current_count >= limit:
                if lockout_seconds > 0:
                    overflow = max(1, current_count - limit + 1)
                    lock_duration = lockout_seconds * (2 ** (overflow - 1))
                    if max_lockout_seconds is not None:
                        lock_duration = min(lock_duration, max_lockout_seconds)
                    self._lockouts[key] = now + lock_duration
                return False
            q.append(now)
            return True


class RedisRateLimiter:
    """Distributed sliding-window limiter backed by Redis + Lua."""

    def __init__(self, redis_url: str, prefix: str = "maestroyoga:rl") -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )
        self._prefix = prefix
        self._script = self._client.register_script(
            """
            local zkey = KEYS[1]
            local lockkey = KEYS[2]
            local now_ms = tonumber(ARGV[1])
            local window_ms = tonumber(ARGV[2])
            local limit = tonumber(ARGV[3])
            local base_lock = tonumber(ARGV[4])
            local max_lock = tonumber(ARGV[5])
            local member = ARGV[6]

            if redis.call('EXISTS', lockkey) == 1 then
              return 0
            end

            redis.call('ZREMRANGEBYSCORE', zkey, '-inf', now_ms - window_ms)
            local count = tonumber(redis.call('ZCARD', zkey))
            if count >= limit then
              if base_lock > 0 then
                local overflow = (count - limit + 1)
                local lock_seconds = base_lock * (2 ^ (overflow - 1))
                if lock_seconds > max_lock then
                  lock_seconds = max_lock
                end
                redis.call('SET', lockkey, '1', 'EX', math.floor(lock_seconds))
              end
              return 0
            end

            redis.call('ZADD', zkey, now_ms, member)
            redis.call('EXPIRE', zkey, math.floor(window_ms / 1000) + max_lock + 1)
            return 1
            """
        )

    def _window_key(self, key: str) -> str:
        return f"{self._prefix}:evt:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self._prefix}:lock:{key}"

    def ping(self) -> bool:
        return bool(self._client.ping())

    def allow(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        lockout_seconds: int = 0,
        max_lockout_seconds: int | None = None,
    ) -> bool:
        lock_key = self._lock_key(key)
        window_key = self._window_key(key)
        now_ms = int(time.time() * 1000)
        max_lock = max_lockout_seconds if max_lockout_seconds is not None else max(lockout_seconds, 1)
        member = f"{now_ms}:{uuid4().hex}"
        result = self._script(
            keys=[window_key, lock_key],
            args=[now_ms, window_seconds * 1000, limit, lockout_seconds, max_lock, member],
        )
        return str(result) == "1"


class ResilientRateLimiter:
    """Uses Redis when available and falls back to memory on failure."""

    def __init__(self, primary: RateLimiter | None, fallback: RateLimiter) -> None:
        self._primary = primary
        self._fallback = fallback

    def allow(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        lockout_seconds: int = 0,
        max_lockout_seconds: int | None = None,
    ) -> bool:
        if self._primary is None:
            return self._fallback.allow(key, limit, window_seconds, lockout_seconds, max_lockout_seconds)
        try:
            return self._primary.allow(key, limit, window_seconds, lockout_seconds, max_lockout_seconds)
        except Exception:
            return self._fallback.allow(key, limit, window_seconds, lockout_seconds, max_lockout_seconds)


def build_rate_limiter() -> RateLimiter:
    backend = os.getenv("RATE_LIMIT_BACKEND", "auto").lower().strip()
    redis_url = os.getenv("REDIS_URL", "").strip()
    prefix = os.getenv("RATE_LIMIT_PREFIX", "maestroyoga:rl").strip() or "maestroyoga:rl"
    memory = InMemoryRateLimiter()

    if backend == "memory":
        return memory

    if backend in {"auto", "redis"} and redis_url and redis is not None:
        redis_limiter = RedisRateLimiter(redis_url=redis_url, prefix=prefix)
        try:
            redis_limiter.ping()
            return ResilientRateLimiter(primary=redis_limiter, fallback=memory)
        except Exception:
            if backend == "redis":
                print("[RATE_LIMITER] Redis unavailable, falling back to memory mode.")
            return memory

    if backend == "redis" and redis is None:
        print("[RATE_LIMITER] redis package missing, falling back to memory mode.")
    return memory


rate_limiter = build_rate_limiter()
