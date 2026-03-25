from typing import List

from Application.dtos import AppointmentResponse
from Domain.interfaces.appointment_repository import IAppointmentRepository
from uuid_extension import UUID7


class ListPatientAppointmentsUseCase:
    def __init__(self, appointment_repo: IAppointmentRepository):
        self.appointment_repo = appointment_repo

    async def execute(self, patient_id: UUID7) -> List[AppointmentResponse]:
        appointments = await self.appointment_repo.list_by_patient(patient_id)
        return [AppointmentResponse.model_validate(a) for a in appointments]
