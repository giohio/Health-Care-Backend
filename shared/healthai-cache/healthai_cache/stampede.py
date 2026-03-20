import redis.asyncio as aioredis
import json
import math
import random
import time
import asyncio
from typing import Any, Callable, TypeVar, Optional

T = TypeVar('T')


class StampedeProtectedCache:
    """
    Cache với 2 lớp bảo vệ chống cache stampede:

    Lớp 1 — Probabilistic Early Recompute (PER):
      Không đợi cache hết hạn mới recompute.
      Càng gần hết TTL → xác suất recompute càng cao.
      → Nhiều request đang active sẽ chia nhau recompute
        trước khi cache hết, không bị "surprise miss" cùng lúc.

    Lớp 2 — Single-Flight:
      Khi cache thực sự miss → chỉ 1 goroutine/coroutine
      được phép query DB. Còn lại chờ kết quả.
      → Tránh N requests cùng lúc đánh vào DB.

    Formula PER:
      now + delta * beta * log(rand()) >= expiry
      → True: recompute (xác suất tăng khi ttl giảm)
      → False: dùng cache

    delta: thời gian recompute lần trước (seconds)
           Cache bao lâu để compute thì PER "nhớ"
           và cố gắng recompute trước khoảng đó.
    beta:  hằng số điều chỉnh aggressiveness.
           beta=1.0 là standard, tăng → recompute sớm hơn.
    """
    BETA = 1.0
    FLIGHT_KEY_PREFIX = "flight"
    FLIGHT_RESULT_PREFIX = "flight_result"

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def get_or_compute(
        self,
        key: str,
        fn: Callable[..., T],
        ttl: int,
        *args,
        **kwargs
    ) -> T:
        """
        Main entry point.

        key: cache key
        fn:  async function để compute value khi cache miss
        ttl: cache TTL tính bằng giây
        """
        # Try cache trước
        cached = await self._get_cached(key)

        if cached is not None:
            value, delta, expiry = cached

            # PER check: có nên recompute sớm không?
            if not self._should_recompute(delta, expiry):
                return value
            # Nếu nên recompute → fall through xuống compute

        # Cache miss hoặc PER triggered → single-flight
        return await self._single_flight(
            key, fn, ttl, *args, **kwargs
        )

    async def _get_cached(
        self,
        key: str
    ) -> Optional[tuple[Any, float, float]]:
        """
        Returns (value, delta, expiry) hoặc None.
        Dùng HGETALL để lấy value + metadata cùng lúc.
        """
        data = await self.redis.hgetall(key)
        if not data:
            return None

        value = json.loads(data[b'v'])
        delta = float(data.get(b'd', 0.001))
        expiry = float(data.get(b'e', 0))
        return value, delta, expiry

    def _should_recompute(
        self,
        delta: float,
        expiry: float
    ) -> bool:
        """
        PER formula.
        Return True nếu nên recompute (xác suất tăng khi gần expire).
        """
        now = time.time()
        # random() ∈ (0, 1) → log là âm
        # -delta * beta * log(rand) là dương
        # Khi now + (positive number) >= expiry → recompute
        gap = expiry - now
        if gap <= 0:
            return True  # Đã expired
        score = -delta * self.BETA * math.log(random.random())
        return score >= gap

    async def _single_flight(
        self,
        key: str,
        fn: Callable,
        ttl: int,
        *args,
        **kwargs
    ) -> Any:
        """
        Chỉ 1 caller được compute, còn lại chờ kết quả.
        """
        flight_key = f"{self.FLIGHT_KEY_PREFIX}:{key}"
        result_key = f"{self.FLIGHT_RESULT_PREFIX}:{key}"

        # Race để trở thành leader
        is_leader = await self.redis.set(
            flight_key, '1', nx=True, ex=30
        )

        if is_leader:
            try:
                t0 = time.monotonic()
                value = await fn(*args, **kwargs)
                delta = time.monotonic() - t0
                expiry = time.time() + ttl

                # Lưu cache với metadata cho PER
                pipe = self.redis.pipeline(transaction=True)
                pipe.hset(key, mapping={
                    'v': json.dumps(value, default=str),   # value
                    'd': str(delta),           # compute time
                    'e': str(expiry)           # expiry timestamp
                })
                pipe.expire(key, ttl)
                # Broadcast kết quả cho waiters
                pipe.set(
                    result_key,
                    json.dumps(value, default=str),
                    ex=30
                )
                await pipe.execute()
                return value
            finally:
                await self.redis.delete(flight_key)
        else:
            # Follower: chờ leader xong
            return await self._wait_for_result(
                result_key, fn, ttl, *args, **kwargs
            )

    async def _wait_for_result(
        self,
        result_key: str,
        fn: Callable,
        ttl: int,
        *args,
        **kwargs
    ) -> Any:
        """
        Poll result_key mỗi 50ms, tối đa 3 giây.
        Fallback: tự compute nếu leader quá chậm.
        """
        for _ in range(60):  # 60 * 50ms = 3s
            await asyncio.sleep(0.05)
            result = await self.redis.get(result_key)
            if result:
                return json.loads(result)

        # Leader quá chậm (>3s) → fallback compute
        return await fn(*args, **kwargs)

    async def invalidate(self, *keys: str):
        """Xóa cache theo exact keys."""
        if keys:
            await self.redis.delete(*keys)

    async def invalidate_pattern(self, pattern: str):
        """
        Xóa cache theo pattern (glob).
        Chú ý: KEYS command scan toàn bộ keyspace.
        Với production data lớn, dùng SCAN thay thế.
        """
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match=pattern, count=100
            )
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break
