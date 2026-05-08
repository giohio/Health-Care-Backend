import redis.asyncio as aioredis

OTP_TTL_SECONDS = 600  # 10 minutes
RESEND_COOLDOWN_SECONDS = 120  # 2 minutes


class OTPRepository:
    """Redis-backed OTP storage for email verification."""

    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    def _key(self, user_id: str, purpose: str = "email_otp") -> str:
        return f"{purpose}:{user_id}"

    def _ttl_key(self, user_id: str, purpose: str = "email_otp") -> str:
        return f"{purpose}_sent_at:{user_id}"

    async def save(self, user_id: str, otp: str, purpose: str = "email_otp") -> None:
        """Store OTP with TTL. Also records sent-at for rate limiting."""
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(self._key(user_id, purpose), otp, ex=OTP_TTL_SECONDS)
            pipe.set(self._ttl_key(user_id, purpose), "1", ex=RESEND_COOLDOWN_SECONDS)
            await pipe.execute()

    async def get(self, user_id: str, purpose: str = "email_otp") -> str | None:
        value = await self._redis.get(self._key(user_id, purpose))
        return value.decode() if isinstance(value, bytes) else value

    async def delete(self, user_id: str, purpose: str = "email_otp") -> None:
        await self._redis.delete(self._key(user_id, purpose), self._ttl_key(user_id, purpose))

    async def is_in_cooldown(self, user_id: str, purpose: str = "email_otp") -> bool:
        """Returns True if a resend is not yet allowed (within cooldown window)."""
        result = await self._redis.exists(self._ttl_key(user_id, purpose))
        return bool(result)
