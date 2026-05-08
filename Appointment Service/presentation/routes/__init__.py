from .appointments import router as appointments_router
from .admin import router as admin_appointments_router

__all__ = ["appointments_router", "admin_appointments_router"]
