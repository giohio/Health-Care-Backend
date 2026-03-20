from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import time
from Domain.value_objects.day_of_week import DayOfWeek

class SpecialtyDTO(BaseModel):
    id: UUID | None = None
    name: str
    description: str | None = None
    
    model_config = ConfigDict(from_attributes=True)

class DoctorDTO(BaseModel):
    user_id: UUID
    full_name: str
    specialty_id: UUID | None = None
    title: str | None = None
    experience_years: int = 0
    
    model_config = ConfigDict(from_attributes=True)

class ScheduleDTO(BaseModel):
    id: UUID | None = None
    doctor_id: UUID
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    slot_duration_minutes: int = 30
    
    model_config = ConfigDict(from_attributes=True)
