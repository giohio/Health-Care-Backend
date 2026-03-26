import uuid
from collections import namedtuple

from Domain.interfaces.appointment_repository import IAppointmentRepository
from infrastructure.clients.appointment_service_client import AppointmentServiceClient
from uuid_extension import UUID7

AppointmentData = namedtuple("AppointmentData", ["patient_id", "doctor_id", "status"])


class AppointmentRepository(IAppointmentRepository):
    def __init__(self, appointment_client: AppointmentServiceClient):
        self.appointment_client = appointment_client

    async def has_completed_appointment(self, patient_id: UUID7, doctor_id: UUID7) -> bool:
        return await self.appointment_client.has_completed_appointment(patient_id, doctor_id)

    async def get_by_id(self, appointment_id: UUID7) -> dict | None:
        data = await self.appointment_client.get_appointment(appointment_id)
        if not data:
            return None
        # Convert dict to a simple object so use-case can access attributes
        return AppointmentData(
            patient_id=uuid.UUID(str(data["patient_id"])),
            doctor_id=uuid.UUID(str(data["doctor_id"])),
            status=data["status"],
        )
