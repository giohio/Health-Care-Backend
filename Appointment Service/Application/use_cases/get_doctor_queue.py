import json
import logging

logger = logging.getLogger(__name__)


def _normalize_cached_payload(cached):
    if isinstance(cached, str):
        return json.loads(cached)
    return cached


class GetDoctorQueueUseCase:
    def __init__(self, appointment_repo, doctor_client, cache=None, emr_client=None):
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client
        self.cache = cache
        self._emr_client = emr_client

    async def execute(self, doctor_id, appointment_date):
        # Don't use cache when EMR client is available to ensure fresh lab_readiness data
        if not self._emr_client and self.cache:
            key = f"queue:{doctor_id}:{appointment_date}"
            cached = await self.cache.get(key)
            if cached:
                return _normalize_cached_payload(cached)

        appointments = await self.appointment_repo.get_doctor_queue(doctor_id, appointment_date)
        data = []
        for appt in appointments:
            patient_context = await self.doctor_client.get_patient_full_context(str(appt.patient_id))

            # Enrich with lab readiness (best-effort)
            lab_readiness = {}
            if self._emr_client is not None:
                try:
                    lab_readiness = await self._emr_client.get_lab_readiness(str(appt.id)) or {}
                except Exception:
                    logger.debug("Could not fetch lab readiness for appointment %s", appt.id)

            data.append(
                {
                    "id": str(appt.id),
                    "appointment_id": str(appt.id),
                    "patient_id": str(appt.patient_id),
                    "patient_name": (patient_context or {}).get("full_name"),
                    "appointment_date": str(appt.appointment_date),
                    "start_time": str(appt.start_time),
                    "end_time": str(appt.end_time),
                    "status": appt.status.value if hasattr(appt.status, "value") else str(appt.status),
                    "queue_number": appt.queue_number,
                    "appointment_type": appt.appointment_type,
                    "chief_complaint": appt.chief_complaint,
                    "lab_readiness": lab_readiness,
                    # AI Triage referral fields
                    "ai_referred": appt.ai_referred,
                    "urgency_level": getattr(appt, "urgency_level", None),
                }
            )
        
        # Only cache if EMR client is not available (no lab readiness data to keep fresh)
        if not self._emr_client and self.cache:
            await self.cache.setex(key, 30, data)
        return data
