class GetDoctorQueueUseCase:
    def __init__(self, appointment_repo, doctor_client):
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client

    async def execute(self, doctor_id, appointment_date):
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
        return data
