import logging
import os
import asyncio
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from presentation.routes import appointments_router
from infrastructure.config import settings
from infrastructure.database.session import AsyncSessionLocal, engine
from shared_lib.messaging import BaseConsumer
from shared_lib.messaging.publisher import BasePublisher
from Application.consumers.appointment_timeout_consumer import AppointmentTimeoutHandler

TRACING_DIR = Path(__file__).resolve().parents[1] / "shared" / "healthai-tracing"
if str(TRACING_DIR) not in sys.path:
    sys.path.append(str(TRACING_DIR))

from telemetry import setup_logging, setup_telemetry

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Appointment Service",
    description="Service for managing medical appointments and schedules",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", "")
)

setup_logging("appointment-service")
setup_telemetry(app, "appointment-service", db_engine=engine)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(appointments_router)

background_tasks = set()


@app.on_event("startup")
async def startup_event():
    async def run_timeout_consumer():
        consumer = BaseConsumer(
            amqp_url=settings.RABBITMQ_URL,
            queue_name="appointment.timeout_checker",
            exchange_name="appointment_events",
            routing_key="appointment.check_timeout",
        )
        handler = AppointmentTimeoutHandler(
            session_factory=AsyncSessionLocal,
            event_publisher=BasePublisher(settings.RABBITMQ_URL),
        )
        await consumer.start(handler_callback=handler.handle)

    task = asyncio.create_task(run_timeout_consumer())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    logger.info("Appointment timeout consumer started")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "appointment-service"}

