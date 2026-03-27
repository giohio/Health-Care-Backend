import redis.asyncio as aioredis
from healthai_cache.idempotency import IdempotencyStore
from healthai_cache.lock import DistributedLock
from healthai_cache.stampede import StampedeProtectedCache


class CacheClient:
    """
    Facade tổng hợp tất cả cache utilities.
    Service chỉ cần inject 1 object này.

    Usage:
        cache = CacheClient.from_url("redis://localhost:6379/0")
        app.state.cache = cache

        # Distributed lock
        async with cache.lock.context("slot:xyz", ttl=15) as acquired:
            if not acquired:
                raise SlotTakenError()

        # Cache with stampede protection
        slots = await cache.smart.get_or_compute(
            key=f"slots:{doctor_id}:{date}",
            fn=fetch_slots_from_db,
            ttl=300,
            doctor_id=doctor_id,
            date=date
        )

        # Idempotency
        cached = await cache.idempotency.get(idem_key)
        if cached:
            return cached
    """

    def __init__(self, redis: aioredis.Redis):
        self._redis = redis
        self.lock = DistributedLock(redis)
        self.smart = StampedeProtectedCache(redis)
        self.idempotency = IdempotencyStore(redis)

    @classmethod
    def from_url(cls, url: str, decode_responses: bool = False, **kwargs) -> "CacheClient":
        r = aioredis.from_url(url, decode_responses=decode_responses, **kwargs)
        return cls(r)

    # Convenience methods
    async def get(self, key: str):
        import json

        val = await self._redis.get(key)
        return json.loads(val) if val else None

    async def set(self, key: str, value, ttl: int = 300):
        import json

        await self._redis.setex(key, ttl, json.dumps(value, default=str))

    async def delete(self, *keys: str):
        if keys:
            await self._redis.delete(*keys)

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def setex(self, key: str, ttl: int, value) -> None:
        await self.set(key, value, ttl=ttl)

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern using SCAN to avoid blocking."""
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    async def close(self):
        await self._redis.aclose()
