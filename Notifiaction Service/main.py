import asyncio
import logging
import os

import aio_pika
from Application.consumers.appointment_events_consumers import (
    AppointmentCancelledConsumer,
    AppointmentConfirmedConsumer,
    AppointmentReminderConsumer,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from healthai_cache import CacheClient
from infrastructure.config import settings
from infrastructure.database.session import AsyncSessionLocal, Base, engine
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    cache = CacheClient.from_url(settings.REDIS_URL)
    app.state.cache = cache

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    app.state.rabbit_connection = connection
    ws_manager = get_ws_manager()

    consumers = [
        AppointmentConfirmedConsumer(connection, cache, AsyncSessionLocal, ws_manager),
        AppointmentCancelledConsumer(connection, cache, AsyncSessionLocal, ws_manager),
        AppointmentReminderConsumer(connection, cache, AsyncSessionLocal, ws_manager),
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
