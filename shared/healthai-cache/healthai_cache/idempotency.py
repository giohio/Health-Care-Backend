import redis.asyncio as aioredis
import json
from typing import Optional


class IdempotencyStore:
    """
    Lưu response của idempotent requests.
    Key = Idempotency-Key header từ client.

    Flow:
    1. Request đến kèm header Idempotency-Key: <uuid>
    2. Check store: đã xử lý chưa?
    3. Nếu có → return cached response ngay
    4. Nếu chưa → xử lý → lưu vào store → return

    TTL mặc định 24h: sau 24h client có thể retry
    với cùng key mà không bị duplicate.
    """
    PREFIX = "idem"

    def __init__(
        self,
        redis: aioredis.Redis,
        default_ttl: int = 86400
    ):
        self.redis = redis
        self.default_ttl = default_ttl

    def _key(self, idempotency_key: str) -> str:
        return f"{self.PREFIX}:{idempotency_key}"

    async def get(
        self,
        idempotency_key: str
    ) -> Optional[dict]:
        """
        Trả về cached response nếu đã xử lý.
        None nếu chưa xử lý.
        """
        val = await self.redis.get(
            self._key(idempotency_key)
        )
        return json.loads(val) if val else None

    async def store(
        self,
        idempotency_key: str,
        status_code: int,
        body: dict,
        ttl: Optional[int] = None
    ):
        """
        Lưu response sau khi xử lý thành công.
        Chỉ lưu 2xx responses.
        """
        if not (200 <= status_code < 300):
            return  # Không cache error responses

        await self.redis.setex(
            self._key(idempotency_key),
            ttl or self.default_ttl,
            json.dumps({
                'status_code': status_code,
                'body': body
            })
        )
