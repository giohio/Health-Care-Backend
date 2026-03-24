import asyncio
import logging
import os
from urllib.parse import urlparse

import aio_pika
from Application.use_cases.create_notification import CreateNotificationUseCase
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from healthai_cache import CacheClient
from infrastructure.config import settings
from infrastructure.consumers import (
    AppointmentAutoConfirmedConsumer,
    AppointmentCancelledConsumer,
    AppointmentCompletedConsumer,
    AppointmentConfirmedConsumer,
    AppointmentCreatedConsumer,
    AppointmentDeclinedConsumer,
    AppointmentNoShowConsumer,
    AppointmentReminderConsumer,
    AppointmentRescheduledConsumer,
    PaymentFailedConsumer,
)
from infrastructure.database.session import AsyncSessionLocal
from infrastructure.email.email_sender import EmailSender
from infrastructure.repositories.notification_repository import NotificationRepository
from presentation.dependencies import get_ws_manager
from presentation.routes import notifications_router, websocket_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Notification Service",
    description="Service for in-app notifications and real-time websocket delivery",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(notifications_router, prefix="/notifications")
app.include_router(websocket_router)

background_tasks = set()


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

    cache = CacheClient.from_url(settings.REDIS_URL)
    app.state.cache = cache

    await wait_for_rabbitmq()

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    app.state.rabbit_connection = connection
    ws_manager = get_ws_manager()
    email_sender = EmailSender()

    def use_case_factory(session):
        repo = NotificationRepository(session)
        return CreateNotificationUseCase(repo, ws_manager, email_sender)

    consumers = [
        AppointmentConfirmedConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentAutoConfirmedConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentCreatedConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentCancelledConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentDeclinedConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentRescheduledConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentNoShowConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentCompletedConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        PaymentFailedConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
        AppointmentReminderConsumer(connection, cache, AsyncSessionLocal, use_case_factory),
    ]

    for consumer in consumers:
        task = asyncio.create_task(consumer.start())
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    logger.info("Notification consumers started")


@app.on_event("shutdown")
async def shutdown_event():
    for task in tuple(background_tasks):
        task.cancel()

    if getattr(app.state, "rabbit_connection", None):
        await app.state.rabbit_connection.close()

    if getattr(app.state, "cache", None):
        await app.state.cache.close()


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "notification-service"}
