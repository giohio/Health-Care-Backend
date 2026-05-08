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
from healthai_cache import CacheClient
from healthai_events import OutboxRelay, RabbitMQPublisher
from infrastructure.config import settings
from infrastructure.consumers import LabOrderPaymentRequiredConsumer, LabOrderCancelledConsumer, PaymentExpiryConsumer, PaymentRefundRequestedConsumer, PaymentRequiredConsumer, create_appointment_status_consumers
from infrastructure.database import models as _db_models  # noqa: F401
from infrastructure.database.session import AsyncSessionLocal, engine
from infrastructure.providers.vnpay_provider import VnpayProvider
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories.payment_repository import PaymentRepository
from presentation.routes.payments import router as payments_router

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


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Payment Service",
    description="Service for managing payments and VNPAY integration",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "payment-service"}

setup_logging("payment-service")
setup_telemetry(app, "payment-service", db_engine=engine)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(payments_router)

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

    def payment_repo_factory(session):
        return PaymentRepository(session)

    # Start consumers
    payment_provider = VnpayProvider()
    event_publisher = OutboxEventPublisher()

    required_consumer = PaymentRequiredConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        payment_repo_factory=payment_repo_factory,
        payment_provider=payment_provider,
        event_publisher=event_publisher,
    )

    expiry_consumer = PaymentExpiryConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        payment_repo_factory=payment_repo_factory,
        event_publisher=event_publisher,
    )

    refund_consumer = PaymentRefundRequestedConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        payment_repo_factory=payment_repo_factory,
        event_publisher=event_publisher,
    )

    appt_status_consumers = create_appointment_status_consumers(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        payment_repo_factory=payment_repo_factory,
    )

    lab_order_payment_consumer = LabOrderPaymentRequiredConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        payment_repo_factory=payment_repo_factory,
        payment_provider=payment_provider,
        event_publisher=event_publisher,
    )

    lab_order_cancelled_consumer = LabOrderCancelledConsumer(
        connection=connection,
        cache=cache,
        session_factory=AsyncSessionLocal,
        payment_repo_factory=payment_repo_factory,
        event_publisher=publisher,
    )

    # Keep strong references to consumers so robust subscriptions can recover after broker restarts.
    app.state.consumers = [required_consumer, expiry_consumer, refund_consumer, lab_order_payment_consumer, lab_order_cancelled_consumer, *appt_status_consumers]

    async def run_consumers():
        try:
            await asyncio.gather(*(consumer.start() for consumer in app.state.consumers))
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Consumer failed: {e}")

    task = asyncio.create_task(run_consumers())
    relay_task = asyncio.create_task(relay.run())
    background_tasks.add(task)
    background_tasks.add(relay_task)
    task.add_done_callback(background_tasks.discard)
    relay_task.add_done_callback(background_tasks.discard)
    logger.info("Payment Service background consumers started.")
    logger.info("Payment outbox relay started")


@app.on_event("shutdown")
async def shutdown_event():
    relay = app.state.relay
    if relay:
        relay.stop()

    for task in tuple(background_tasks):
        task.cancel()

    if app.state.rabbit_connection:
        await app.state.rabbit_connection.close()
    if app.state.publisher:
        await app.state.publisher.close()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
