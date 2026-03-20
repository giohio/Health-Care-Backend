from .specialties import router as specialties_router
from .doctors import router as doctors_router
from .schedules import router as schedules_router

__all__ = ["specialties_router", "doctors_router", "schedules_router"]
