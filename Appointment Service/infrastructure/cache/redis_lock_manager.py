import redis.asyncio as aioredis
from Domain.interfaces.lock_manager import ILockManager
import logging

logger = logging.getLogger(__name__)

class RedisLockManager(ILockManager):
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url, decode_responses=True)

    async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        try:
            return await self.redis.set(key, "LOCKED", nx=True, ex=ttl_seconds)
        except Exception as e:
            logger.error(f"Failed to acquire lock: {str(e)}")
            return False

    async def release_lock(self, key: str) -> bool:
        try:
            return await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to release lock: {str(e)}")
            return False