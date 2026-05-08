import asyncio
import importlib.util
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import aio_pika
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from healthai_cache import CacheClient
from healthai_events import RabbitMQPublisher
from infrastructure.config import settings
from infrastructure.consumers import LabPaymentPaidConsumer
from infrastructure.database import models as _db_models  # noqa: F401
from infrastructure.database.session import engine
from infrastructure.messaging.publisher import EmrEventPublisher
from presentation.routes import emr_router

TRACING_DIR = Path(__file__).resolve().parents[1] / "shared" / "healthai-tracing"
TELEMETRY_PATH = TRACING_DIR / "telemetry.py"

if TELEMETRY_PATH.exists():
    spec = importlib.util.spec_from_file_location("healthai_tracing_telemetry", TELEMETRY_PATH)
    telemetry_module = importlib.util.module_from_spec(spec) if spec and spec.loader else None
    if spec and spec.loader and telemetry_module:
        spec.loader.exec_module(telemetry_module)
        setup_logging = telemetry_module.setup_logging
        setup_telemetry = telemetry_module.setup_telemetry
    else:
        telemetry_module = None

if not TELEMETRY_PATH.exists() or telemetry_module is None:

    def setup_logging(*_args, **_kwargs):
        return None

    def setup_telemetry(*_args, **_kwargs):
        return None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="EMR Result Service",
    description="Service for managing lab orders, lab results, and the Human-in-the-Loop AI review workflow.",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
)

setup_logging("emr-result-service")
setup_telemetry(app, "emr-result-service", db_engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/lab-orders/health")
@app.get("/lab-results/health")
async def health_check():
    return {"status": "healthy", "service": "emr-result-service"}


app.include_router(emr_router)

# Serve uploaded files at /uploads — works for local storage
_upload_dir = Path(settings.UPLOAD_DIR)
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")

background_tasks: set = set()
app.state.event_publisher = None
app.state.rabbit_connection = None
app.state.cache = None


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

    rabbit_publisher = await RabbitMQPublisher.connect(settings.RABBITMQ_URL)
    app.state.event_publisher = EmrEventPublisher(rabbit_publisher)

    # Wire up LabPaymentPaidConsumer with session factory and repository factory
    from infrastructure.database.session import AsyncSessionLocal
    from infrastructure.repositories.lab_order_repository import LabOrderRepository

    def order_repo_factory(session):
        return LabOrderRepository(session)

    lab_payment_consumer = LabPaymentPaidConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        order_repo_factory=order_repo_factory,
    )

    task = asyncio.create_task(lab_payment_consumer.start())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    logger.info("EMR consumers started")


@app.on_event("shutdown")
async def shutdown_event():
    for task in tuple(background_tasks):
        task.cancel()
    if getattr(app.state, "rabbit_connection", None):
        await app.state.rabbit_connection.close()
    if getattr(app.state, "cache", None):
        await app.state.cache.close()

