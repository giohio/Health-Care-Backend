from Domain.interfaces.lock_manager import ILockManager
from healthai_cache import CacheClient


class RedisLockManager(ILockManager):
    """Slot lock adapter backed by healthai_cache.DistributedLock."""

    SLOT_LOCK_TTL = 10

    def __init__(self, cache: CacheClient):
        self._lock = cache.lock
        self._tokens: dict[str, str] = {}

    async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        token = await self._lock.acquire(key, ttl=ttl_seconds)
        if not token:
            return False
        self._tokens[key] = token
        return True

    async def release_lock(self, key: str) -> bool:
        token = self._tokens.pop(key, None)
        if not token:
            return False
        return await self._lock.release(key, token)

    def _slot_key(self, doctor_id: str, appointment_date: str, start_time: str) -> str:
        return f"slot:{doctor_id}:{appointment_date}:{start_time}"

    async def acquire_slot(self, doctor_id: str, appointment_date: str, start_time: str) -> str | None:
        return await self._lock.acquire(
            self._slot_key(doctor_id, appointment_date, start_time),
            ttl=self.SLOT_LOCK_TTL,
        )

    async def release_slot(
        self,
        doctor_id: str,
        appointment_date: str,
        start_time: str,
        token: str,
    ) -> bool:
        return await self._lock.release(
            self._slot_key(doctor_id, appointment_date, start_time),
            token,
        )
