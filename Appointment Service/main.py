import logging
import os
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from presentation.routes import appointments_router

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Appointment Service",
    description="Service for managing medical appointments and schedules",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", "")
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(appointments_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "appointment-service"}

