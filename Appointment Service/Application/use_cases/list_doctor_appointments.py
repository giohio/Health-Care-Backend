from datetime import date
from typing import List

from Application.dtos import AppointmentResponse
from Domain.interfaces.appointment_repository import IAppointmentRepository
from uuid_extension import UUID7


class ListDoctorAppointmentsUseCase:
    def __init__(self, appointment_repo: IAppointmentRepository):
        self.appointment_repo = appointment_repo

    async def execute(
        self, doctor_id: UUID7, date_from: date | None = None, date_to: date | None = None
    ) -> List[AppointmentResponse]:
        appointments = await self.appointment_repo.list_by_doctor(doctor_id, date_from, date_to)
        return [AppointmentResponse.model_validate(a) for a in appointments]
