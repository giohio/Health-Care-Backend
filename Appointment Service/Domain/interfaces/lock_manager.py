from abc import ABC, abstractmethod


class ILockManager(ABC):
    @abstractmethod
    async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        """Acquire a lock with a specified time-to-live (TTL) in seconds."""

    @abstractmethod
    async def release_lock(self, key: str) -> bool:
        """Release a lock."""

    @abstractmethod
    async def acquire_slot(self, doctor_id: str, appointment_date: str, start_time: str) -> str | None:
        """Acquire a slot lock and return lock token if successful."""

    @abstractmethod
    async def release_slot(
        self,
        doctor_id: str,
        appointment_date: str,
        start_time: str,
        token: str,
    ) -> bool:
        """Release a slot lock if the caller owns the token."""
