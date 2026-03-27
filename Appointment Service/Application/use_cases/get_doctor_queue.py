import json


def _normalize_cached_payload(cached):
    if isinstance(cached, str):
        return json.loads(cached)
    return cached


class GetDoctorQueueUseCase:
    def __init__(self, appointment_repo, doctor_client, cache=None):
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client
        self.cache = cache

    async def execute(self, doctor_id, appointment_date):
        if self.cache:
            key = f"queue:{doctor_id}:{appointment_date}"
            cached = await self.cache.get(key)
            if cached:
                return _normalize_cached_payload(cached)

        appointments = await self.appointment_repo.get_doctor_queue(doctor_id, appointment_date)
        data = []
        for appt in appointments:
            patient_context = await self.doctor_client.get_patient_full_context(str(appt.patient_id))
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
                }
            )
        if self.cache:
            await self.cache.setex(key, 30, data)
        return data
