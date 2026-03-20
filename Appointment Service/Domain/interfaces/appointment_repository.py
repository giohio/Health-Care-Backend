from abc import ABC, abstractmethod
from typing import List, Optional
from Domain.entities.appointment import Appointment
from uuid_extension import UUID7
from datetime import date, time

class IAppointmentRepository(ABC):
    @abstractmethod
    async def save(self, appointment: Appointment) -> Appointment:
        pass

    @abstractmethod
    async def get_by_id(self, appointment_id: UUID7) -> Optional[Appointment]:
        pass

    @abstractmethod
    async def list_by_patient(self, patient_id: UUID7) -> List[Appointment]:
        pass

    @abstractmethod
    async def check_doctor_availability(self, doctor_id: UUID7, appointment_date: date, start_time: time) -> bool:
        """Returns True if the doctor is FREE at the given time."""
        pass
