import asyncio
import logging
import os
import sys
from pathlib import Path

import aio_pika
from Application.consumers.appointment_timeout_consumer import AppointmentTimeoutConsumer
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from healthai_cache import CacheClient
from healthai_events import OutboxRelay, RabbitMQPublisher
from infrastructure.config import settings
from infrastructure.database.session import AsyncSessionLocal, engine
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

# Routes
app.include_router(appointments_router)

background_tasks = set()
app.state.cache = None
app.state.rabbit_connection = None
app.state.publisher = None
app.state.relay = None


@app.on_event("startup")
async def startup_event():
    cache = CacheClient.from_url(settings.REDIS_URL)
    app.state.cache = cache

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    app.state.rabbit_connection = connection

    publisher = await RabbitMQPublisher.connect(settings.RABBITMQ_URL)
    app.state.publisher = publisher

    relay = OutboxRelay(session_factory=AsyncSessionLocal, publisher=publisher)
    app.state.relay = relay

    timeout_consumer = AppointmentTimeoutConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
    )

    task = asyncio.create_task(timeout_consumer.start())
    relay_task = asyncio.create_task(relay.run())
    background_tasks.add(task)
    background_tasks.add(relay_task)
    task.add_done_callback(background_tasks.discard)
    relay_task.add_done_callback(background_tasks.discard)
    logger.info("Appointment timeout consumer started")
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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "appointment-service"}
