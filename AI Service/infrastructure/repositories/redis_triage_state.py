"""RedisTriageStateRepository — Redis-backed implementation of ITriageStateRepository.

Uses ``redis.asyncio`` with a class-level connection pool singleton so all
instances share a single pool (one per process), matching the WokuClient pattern.

Key scheme:
  triage:pending:{patient_id}   TTL 1800 s  (pending slot selection)
  triage:rec:{patient_id}       TTL 3600 s  (last recommendation cache)
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from Domain.interfaces.triage_state_repository import ITriageStateRepository
from infrastructure.config import get_settings

logger = logging.getLogger(__name__)

_PENDING_TTL = 1800   # 30 min — session window for slot confirmation
_REC_TTL     = 3600   # 1 hour — matches _RECOMMENDATION_TTL_SECONDS in symptom_check


class RedisTriageStateRepository(ITriageStateRepository):
    """Thread-safe, multi-worker implementation backed by Redis.

    A class-level Redis client is created lazily on first use and reused
    across all instances (same pattern as WokuClient._shared_openai).
    """

    _client: aioredis.Redis | None = None

    @classmethod
    def _get_client(cls) -> aioredis.Redis:
        if cls._client is None:
            s = get_settings()
            cls._client = aioredis.from_url(
                s.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return cls._client

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _pending_key(patient_id: str) -> str:
        return f"triage:pending:{patient_id}"

    @staticmethod
    def _rec_key(patient_id: str) -> str:
        return f"triage:rec:{patient_id}"

    # ── Pending slots ─────────────────────────────────────────────────────────

    async def get_pending_slots(self, patient_id: str) -> Optional[dict]:
        try:
            raw = await self._get_client().get(self._pending_key(patient_id))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.error("Redis get_pending_slots error (patient=%s): %s", patient_id, exc)
            return None

    async def set_pending_slots(self, patient_id: str, data: dict) -> None:
        try:
            await self._get_client().setex(
                self._pending_key(patient_id),
                _PENDING_TTL,
                json.dumps(data),
            )
        except Exception as exc:
            logger.error("Redis set_pending_slots error (patient=%s): %s", patient_id, exc)

    async def del_pending_slots(self, patient_id: str) -> None:
        try:
            await self._get_client().delete(self._pending_key(patient_id))
        except Exception as exc:
            logger.error("Redis del_pending_slots error (patient=%s): %s", patient_id, exc)

    # ── Recommendation cache ──────────────────────────────────────────────────

    async def get_recommendation(self, patient_id: str) -> Optional[dict]:
        try:
            raw = await self._get_client().get(self._rec_key(patient_id))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.error("Redis get_recommendation error (patient=%s): %s", patient_id, exc)
            return None

    async def set_recommendation(self, patient_id: str, data: dict) -> None:
        try:
            await self._get_client().setex(
                self._rec_key(patient_id),
                _REC_TTL,
                json.dumps(data),
            )
        except Exception as exc:
            logger.error("Redis set_recommendation error (patient=%s): %s", patient_id, exc)

    async def del_recommendation(self, patient_id: str) -> None:
        try:
            await self._get_client().delete(self._rec_key(patient_id))
        except Exception as exc:
            logger.error("Redis del_recommendation error (patient=%s): %s", patient_id, exc)
