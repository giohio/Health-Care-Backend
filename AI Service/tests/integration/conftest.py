"""
Shared fixtures for AI Service integration tests.

Creates a minimal FastAPI test application that:
  - Uses the real routers from presentation/routes/
  - Provides FastAPI dependency overrides to inject Fake use cases
  - Never calls real LLM APIs or Celery broker
"""

import asyncio
import pytest
import pytest_asyncio
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from presentation.routes import (
    symptom_router,
    lab_router,
    emr_router,
    lab_chat_router,
    clinical_assist_router,
    speech_router,
    auscultation_router,
)


def create_test_app() -> FastAPI:
    """Minimal app with all AI routes — no telemetry middleware for speed."""
    app = FastAPI(title="AI Service – Tests")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(symptom_router)
    app.include_router(lab_router)
    app.include_router(emr_router)
    app.include_router(lab_chat_router)
    app.include_router(clinical_assist_router)
    app.include_router(speech_router)
    app.include_router(auscultation_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "ai_service"}

    return app


@pytest.fixture(scope="module")
def app():
    return create_test_app()


@pytest_asyncio.fixture(scope="module")
async def client(app):
    """Shared httpx.AsyncClient backed by ASGI transport — no real network."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
