import asyncio
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.config import settings
from presentation.routes import auth_router
from shared_lib.messaging import BaseConsumer
from infrastructure import AsyncSessionLocal, UserRepository
from infrastructure.database.session import engine
from Application.event_handlers.profile_completed import ProfileCompletedHandler

import os

TRACING_DIR = Path(__file__).resolve().parents[1] / "shared" / "healthai-tracing"
if str(TRACING_DIR) not in sys.path:
    sys.path.append(str(TRACING_DIR))

from telemetry import setup_logging, setup_telemetry

app = FastAPI(
    title="Auth Service",
    description="Authentication and Identity Provider Service",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", "")
)

setup_logging("auth-service")
setup_telemetry(app, "auth-service", db_engine=engine)

# Keep track of background tasks to prevent garbage collection
background_tasks = set()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router)


@app.on_event("startup")
async def startup_event():
    # Start RabbitMQ Consumer in a background task
    async def run_consumer():
        async with AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            handler = ProfileCompletedHandler(user_repo)
            
            consumer = BaseConsumer(
                amqp_url=settings.RABBITMQ_URL,
                queue_name="auth_profile_completion_queue",
                exchange_name="user_events",
                routing_key="profile.completed"
            )
            
            try:
                await consumer.start(handler_callback=handler.handle)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Auth Consumer failed: {e}")

    task = asyncio.create_task(run_consumer())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "auth-service"}
