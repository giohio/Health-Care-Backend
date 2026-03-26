from abc import ABC, abstractmethod

from uuid_extension import UUID7


class IAppointmentRepository(ABC):
    @abstractmethod
    async def has_completed_appointment(self, patient_id: UUID7, doctor_id: UUID7) -> bool:
        pass
