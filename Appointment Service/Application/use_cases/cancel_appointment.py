from uuid_extension import UUID7
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.exceptions.domain_exceptions import AppointmentNotFoundException
from Domain.value_objects.appointment_status import AppointmentStatus
from Application.dtos import AppointmentResponse

class CancelAppointmentUseCase:
    def __init__(self, appointment_repo: IAppointmentRepository):
        self.appointment_repo = appointment_repo

    async def execute(self, appointment_id: UUID7) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()
        
        appointment.status = AppointmentStatus.CANCELLED
        await self.appointment_repo.save(appointment)
        
        return AppointmentResponse.model_validate(appointment)
