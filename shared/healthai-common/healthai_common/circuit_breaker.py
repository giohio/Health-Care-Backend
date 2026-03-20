import logging
import time
from typing import Callable, Optional, TypeVar, Any
from healthai_cache import CacheClient

logger = logging.getLogger(__name__)
T = TypeVar('T')


class CircuitOpenError(Exception):
    """Raised when circuit is OPEN."""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern cho HTTP calls giữa services.

    States:
      CLOSED   → bình thường, requests pass through
      OPEN     → đang fail, block requests luôn
      HALF_OPEN → testing recovery, cho 1 request qua

    Transition:
      CLOSED → OPEN:      failures >= threshold
      OPEN → HALF_OPEN:   sau recovery_timeout giây
      HALF_OPEN → CLOSED: request thành công
      HALF_OPEN → OPEN:   request thất bại

    State lưu trong Redis để share giữa các instances
    của cùng service.

    Usage:
        cb = CircuitBreaker(
            name='doctor_service',
            cache=cache,
            failure_threshold=5,
            recovery_timeout=30
        )

        result = await cb.call(
            fn=doctor_client.get_slots,
            fallback=get_slots_from_local_cache,
            doctor_id=...,
            date=...
        )
    """
    def __init__(
        self,
        name: str,
        cache: CacheClient,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
    ):
        self.name = name
        self.cache = cache
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    @property
    def _state_key(self) -> str:
        return f"cb:{self.name}:state"

    @property
    def _failure_key(self) -> str:
        return f"cb:{self.name}:failures"

    @property
    def _half_open_key(self) -> str:
        return f"cb:{self.name}:half_open_lock"

    async def get_state(self) -> str:
        state = await self.cache.get(self._state_key)
        return state or 'CLOSED'

    async def call(
        self,
        fn: Callable[..., T],
        fallback: Optional[Callable[..., T]] = None,
        *args,
        **kwargs
    ) -> T:
        state = await self.get_state()

        if state == 'OPEN':
            logger.warning(
                f"Circuit {self.name} OPEN — "
                f"blocking request"
            )
            if fallback:
                return await fallback(*args, **kwargs)
            raise CircuitOpenError(
                f"Service {self.name} is unavailable"
            )

        if state == 'HALF_OPEN':
            # Chỉ cho 1 probe request qua
            is_probe = await self.cache._redis.set(
                self._half_open_key, '1',
                nx=True, ex=self.recovery_timeout
            )
            if not is_probe:
                if fallback:
                    return await fallback(*args, **kwargs)
                raise CircuitOpenError(
                    f"Circuit {self.name} HALF_OPEN "
                    f"— probe in progress"
                )

        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure(state)
            if fallback:
                return await fallback(*args, **kwargs)
            raise

    async def _on_success(self):
        """Reset về CLOSED state."""
        await self.cache.delete(
            self._state_key,
            self._failure_key,
            self._half_open_key
        )
        logger.info(f"Circuit {self.name} → CLOSED")

    async def _on_failure(self, current_state: str):
        """Tăng failure count, chuyển OPEN nếu đủ."""
        failures = await self.cache._redis.incr(
            self._failure_key
        )
        await self.cache._redis.expire(
            self._failure_key,
            self.recovery_timeout * 4
        )

        if current_state == 'HALF_OPEN' or \
           failures >= self.failure_threshold:
            # Chuyển OPEN, tự động thử lại sau recovery_timeout
            await self.cache.set(
                self._state_key, 'OPEN',
                ttl=self.recovery_timeout
            )
            logger.error(
                f"Circuit {self.name} → OPEN "
                f"(failures: {failures})"
            )
