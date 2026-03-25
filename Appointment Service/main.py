import asyncio
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import aio_pika
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from healthai_cache import CacheClient
from healthai_events import OutboxRelay, RabbitMQPublisher
from infrastructure.clients.doctor_service_client import DoctorServiceClient
from infrastructure.config import settings
from infrastructure.consumers import (
    AppointmentTimeoutConsumer,
    PaymentExpiredConsumer,
    PaymentFailedConsumer,
    PaymentPaidConsumer,
    PaymentTimeoutConsumer,
)
from infrastructure.database import models as _db_models  # noqa: F401
from infrastructure.database.session import AsyncSessionLocal
from infrastructure.database.session import engine
from infrastructure.repositories.appointment_repository import AppointmentRepository
from presentation.routes import appointments_router

TRACING_DIR = Path(__file__).resolve().parents[1] / "shared" / "healthai-tracing"
if str(TRACING_DIR) not in sys.path:
    sys.path.append(str(TRACING_DIR))

from telemetry import setup_logging, setup_telemetry  # noqa: E402

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Appointment Service",
    description="Service for managing medical appointments and schedules",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "appointment-service"}

# Routes
app.include_router(appointments_router)

background_tasks = set()
app.state.cache = None
app.state.rabbit_connection = None
app.state.publisher = None
app.state.relay = None
app.state.consumers = []


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

    cache = CacheClient.from_url(settings.REDIS_URL)
    app.state.cache = cache

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    app.state.rabbit_connection = connection

    publisher = await RabbitMQPublisher.connect(settings.RABBITMQ_URL)
    app.state.publisher = publisher

    relay = OutboxRelay(session_factory=AsyncSessionLocal, publisher=publisher)
    app.state.relay = relay

    def appointment_repo_factory(session):
        return AppointmentRepository(session)

    doctor_client = DoctorServiceClient(cache=cache)

    timeout_consumer = AppointmentTimeoutConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        appointment_repo_factory=appointment_repo_factory,
    )
    payment_paid_consumer = PaymentPaidConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        appointment_repo_factory=appointment_repo_factory,
        doctor_client=doctor_client,
    )
    payment_failed_consumer = PaymentFailedConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        appointment_repo_factory=appointment_repo_factory,
    )
    payment_expired_consumer = PaymentExpiredConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        appointment_repo_factory=appointment_repo_factory,
    )
    payment_timeout_consumer = PaymentTimeoutConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        appointment_repo_factory=appointment_repo_factory,
    )

    # Keep strong references to consumers so robust subscriptions survive after startup and broker restarts.
    app.state.consumers = [
        timeout_consumer,
        payment_paid_consumer,
        payment_failed_consumer,
        payment_expired_consumer,
        payment_timeout_consumer,
    ]

    async def run_consumers():
        try:
            await asyncio.gather(*(consumer.start() for consumer in app.state.consumers))
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Appointment consumers failed: %s", exc)

    task = asyncio.create_task(run_consumers())
    relay_task = asyncio.create_task(relay.run())
    background_tasks.add(task)
    background_tasks.add(relay_task)
    task.add_done_callback(background_tasks.discard)
    relay_task.add_done_callback(background_tasks.discard)
    logger.info("Appointment timeout consumer started")
    logger.info("Appointment payment consumers started")
    logger.info("Outbox relay started")


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

    connection = app.state.rabbit_connection
    if connection:
        await connection.close()

    cache = app.state.cache
    if cache:
        await cache.close()
