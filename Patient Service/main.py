import asyncio
import logging
import os
import sys
from pathlib import Path

from Application import InitializeProfileUseCase, UserRegisteredHandler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.config import settings
from infrastructure.database.session import AsyncSessionLocal, engine
from infrastructure.repositories.repositories import PatientHealthRepository, PatientProfileRepository
from presentation.routes import internal, patient
from shared_lib.messaging import BaseConsumer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TRACING_DIR = Path(__file__).resolve().parents[1] / "shared" / "healthai-tracing"
if str(TRACING_DIR) not in sys.path:
    sys.path.append(str(TRACING_DIR))

from telemetry import setup_logging, setup_telemetry  # noqa: E402

app = FastAPI(
    title="Patient Profile Service",
    description="Service for managing patient demographics and health backgrounds",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
)

setup_logging("patient-service")
setup_telemetry(app, "patient-service", db_engine=engine)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(patient.router)
app.include_router(internal.router)


@app.on_event("startup")
async def startup_event():
    # 1. Start RabbitMQ Consumer in a background task
    async def run_consumer():
        async with AsyncSessionLocal() as session:
            profile_repo = PatientProfileRepository(session)
            health_repo = PatientHealthRepository(session)
            init_use_case = InitializeProfileUseCase(profile_repo, health_repo)
            handler = UserRegisteredHandler(init_use_case)

            consumer = BaseConsumer(
                amqp_url=settings.RABBITMQ_URL,
                queue_name="patient_service_register_queue",
                exchange_name="user_events",
                routing_key="user.registered",
            )

            try:
                await consumer.start(handler_callback=handler.handle)
            except Exception as e:
                logger.error(f"Consumer failed to start: {e}")

    # Store task to prevent premature garbage collection
    task = asyncio.create_task(run_consumer())
    app.state.consumer_task = task
    logger.info("RabbitMQ Consumer task started in background.")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "patient-service"}
