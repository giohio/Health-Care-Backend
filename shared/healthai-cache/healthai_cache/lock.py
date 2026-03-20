import redis.asyncio as aioredis
from uuid_extension import uuid7
from typing import Optional
from contextlib import asynccontextmanager

# Lua script để release lock an toàn
# Chỉ delete nếu value khớp — tránh delete lock của người khác
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class DistributedLock:
    """
    Redis distributed lock với Lua-based release.

    Vấn đề Lua giải quyết:
    1. GET lock_key  → value khớp
    2. ... network hiccup, lock expired, người khác lock ...
    3. DEL lock_key  → XÓA NHẦM LOCK CỦA NGƯỜI KHÁC!

    Lua script GET+DEL là atomic nên vấn đề trên không xảy ra.

    Usage (manual):
        lock = DistributedLock(redis)
        token = await lock.acquire("slot:doc1:2025-03-19:10:00")
        if not token:
            raise SlotTakenError()
        try:
            ... business logic ...
        finally:
            await lock.release("slot:doc1:2025-03-19:10:00", token)

    Usage (context manager — recommended):
        async with lock.context("slot:doc1:2025:10:00", ttl=15) as acquired:
            if not acquired:
                raise SlotTakenError()
            ... business logic ...
    """
    PREFIX = "lock"

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self._release_script = self.redis.register_script(
            _RELEASE_SCRIPT
        )

    def _key(self, name: str) -> str:
        return f"{self.PREFIX}:{name}"

    async def acquire(
        self,
        name: str,
        ttl: int = 15
    ) -> Optional[str]:
        """
        Trả về lock_token nếu acquire thành công.
        Trả về None nếu slot đã bị lock.

        ttl: thời gian lock tự động expire (seconds)
             Đảm bảo lock không bị giữ mãi nếu app crash.
        """
        token = str(uuid7())
        acquired = await self.redis.set(
            self._key(name),
            token,
            nx=True,   # Only set if Not eXists
            ex=ttl
        )
        return token if acquired else None

    async def release(
        self,
        name: str,
        token: str
    ) -> bool:
        """
        Chỉ release nếu token khớp (chính chủ).
        Return True nếu release thành công.
        """
        result = await self._release_script(
            keys=[self._key(name)],
            args=[token]
        )
        return bool(result)

    async def extend(
        self,
        name: str,
        token: str,
        additional_ttl: int
    ) -> bool:
        """
        Gia hạn TTL của lock nếu vẫn còn là owner.
        Dùng khi operation mất nhiều hơn TTL ban đầu.
        """
        extend_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await self.redis.eval(
            extend_script,
            1,
            self._key(name),
            token,
            str(additional_ttl)
        )
        return bool(result)

    @asynccontextmanager
    async def context(
        self,
        name: str,
        ttl: int = 15
    ):
        """
        Context manager — tự động release khi exit.

        Yields True nếu acquired, False nếu không.
        Caller quyết định raise exception hay không.
        """
        token = await self.acquire(name, ttl)
        try:
            yield token is not None
        finally:
            if token:
                await self.release(name, token)
