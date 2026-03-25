import asyncio
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from Application.event_handlers.user_registered import UserRegisteredHandler
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from healthai_events import BaseConsumer, OutboxRelay, RabbitMQPublisher
from infrastructure.config import settings
from infrastructure.database.session import AsyncSessionLocal, engine
from infrastructure.repositories import DoctorRepository
from presentation.routes import doctors_router, schedules_router, specialties_router


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
app.state.publisher = None
app.state.relay = None


@app.on_event("startup")
async def startup_event():
    async def wait_for_rabbitmq(max_attempts: int = 60, delay_seconds: int = 2) -> None:
        parsed = urlparse(settings.RABBITMQ_URL)
        host = parsed.hostname or "rabbitmq"
        port = parsed.port or 5672

        for attempt in range(1, max_attempts + 1):
            try:
                _, writer = await asyncio.open_connection(host, port)
                writer.close()
                await writer.wait_closed()
                logger.info("RabbitMQ is reachable at %s:%s", host, port)
                return
            except Exception:
                logger.info("Waiting for RabbitMQ (%s/%s) at %s:%s...", attempt, max_attempts, host, port)
                await asyncio.sleep(delay_seconds)

        raise RuntimeError(f"RabbitMQ is not reachable at {host}:{port} after {max_attempts} attempts")

    await wait_for_rabbitmq()

    publisher = await RabbitMQPublisher.connect(settings.RABBITMQ_URL)
    app.state.publisher = publisher

    relay = OutboxRelay(session_factory=AsyncSessionLocal, publisher=publisher)
    app.state.relay = relay
    relay_task = asyncio.create_task(relay.run())
    background_tasks.add(relay_task)
    relay_task.add_done_callback(background_tasks.discard)

    # Start RabbitMQ Consumer in a background task
    async def run_consumer():
        while True:
            try:
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

                await consumer.start(handler_callback=handler.handle)
            except Exception as e:
                logger.error("Doctor Consumer failed: %s", e)
                await asyncio.sleep(5)

    task = asyncio.create_task(run_consumer())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    logger.info("Doctor Service background consumer started.")


@app.on_event("shutdown")
async def shutdown_event():
    relay = app.state.relay
    if relay:
        relay.stop()

    for task in tuple(background_tasks):
        task.cancel()

    publisher = app.state.publisher
    if publisher:
        await publisher.close()


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "doctor-service"}
