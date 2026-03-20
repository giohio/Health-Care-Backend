from abc import ABC, abstractmethod

class ILockManager(ABC):
    @abstractmethod
    async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        """Acquire a lock with a specified time-to-live (TTL) in seconds."""
        pass

    @abstractmethod
    async def release_lock(self, key: str) -> bool:
        """Release a lock."""
        pass