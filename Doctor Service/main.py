import asyncio
import logging
import os
import sys
from pathlib import Path

from Application.event_handlers.user_registered import UserRegisteredHandler
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.config import settings
from infrastructure.database.session import AsyncSessionLocal, engine
from infrastructure.repositories import DoctorRepository
from presentation.routes import doctors_router, schedules_router, specialties_router
from shared_lib.messaging import BaseConsumer

TRACING_DIR = Path(__file__).resolve().parents[1] / "shared" / "healthai-tracing"
if str(TRACING_DIR) not in sys.path:
    sys.path.append(str(TRACING_DIR))

from telemetry import setup_logging, setup_telemetry  # noqa: E402

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Doctor Service",
    description="Service for managing medical specialties, doctors, and schedules",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
)

setup_logging("doctor-service")
setup_telemetry(app, "doctor-service", db_engine=engine)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(specialties_router)
app.include_router(doctors_router)
app.include_router(schedules_router)

background_tasks = set()


@app.on_event("startup")
async def startup_event():
    # Start RabbitMQ Consumer in a background task
    async def run_consumer():
        async with AsyncSessionLocal() as session:
            doctor_repo = DoctorRepository(session)
            register_use_case = RegisterDoctorUseCase(doctor_repo)
            handler = UserRegisteredHandler(register_use_case)

            consumer = BaseConsumer(
                amqp_url=settings.RABBITMQ_URL,
                queue_name="doctor_service_user_queue",
                exchange_name="user_events",
                routing_key="user.registered",
            )

            try:
                await consumer.start(handler_callback=handler.handle)
            except Exception as e:
                logger.error(f"Doctor Consumer failed: {e}")

    task = asyncio.create_task(run_consumer())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    logger.info("Doctor Service background consumer started.")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "doctor-service"}
