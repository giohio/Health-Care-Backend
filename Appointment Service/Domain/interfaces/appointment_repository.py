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

    @abstractmethod
    async def get_by_id_with_lock(self, appointment_id: UUID7) -> Optional[Appointment]:
        """Fetch one appointment row with SELECT FOR UPDATE lock."""
        pass

    @abstractmethod
    async def is_slot_taken(
        self,
        doctor_id: UUID7,
        appointment_date: date,
        start_time: time,
        end_time: time,
        exclude_id: UUID7 | None = None,
    ) -> bool:
        """Return True if any active booking overlaps the given slot range."""
        pass

    @abstractmethod
    async def get_next_queue_number(self, doctor_id: UUID7, appointment_date: date) -> int:
        """Return next queue number for confirmed appointments on a date."""
        pass

    @abstractmethod
    async def get_doctor_queue(self, doctor_id: UUID7, appointment_date: date) -> list[Appointment]:
        """List doctor appointments for the date ordered by pending first then time."""
        pass

    @abstractmethod
    async def get_booked_slots(
        self,
        doctor_id: UUID7,
        appointment_date: date,
    ) -> list[tuple[time, time]]:
        """Return booked time ranges for active appointments."""
        pass
