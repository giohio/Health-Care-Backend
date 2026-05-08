import logging
import os
import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.config import settings
from presentation.routes import (
    symptom_router,
    lab_router,
    lab_suggestion_router,
    emr_router,
    triage_sessions_router,
    lab_chat_router,
    clinical_assist_router,
    speech_router,
    auscultation_router,
    treatment_plan_router,
    all_labs_router,
    soap_router,
)

TRACING_DIR = Path(__file__).resolve().parents[1] / "shared" / "healthai-tracing"
TELEMETRY_PATH = TRACING_DIR / "telemetry.py"

if TELEMETRY_PATH.exists():
    spec = importlib.util.spec_from_file_location("healthai_tracing_telemetry", TELEMETRY_PATH)
    telemetry_module = importlib.util.module_from_spec(spec) if spec and spec.loader else None
    if spec and spec.loader and telemetry_module:
        try:
            spec.loader.exec_module(telemetry_module)
            setup_logging = telemetry_module.setup_logging
            setup_telemetry = telemetry_module.setup_telemetry
        except Exception:
            telemetry_module = None
    else:
        telemetry_module = None

if not TELEMETRY_PATH.exists() or telemetry_module is None:

    def setup_logging(*_args, **_kwargs):
        return None

    def setup_telemetry(*_args, **_kwargs):
        return None

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Service",
    description="Clinical AI pipeline: triage, lab analysis, EMR summarization.",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
)

setup_logging("ai-service")
setup_telemetry(app, "ai-service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(symptom_router)
app.include_router(lab_router)
app.include_router(lab_suggestion_router)
app.include_router(emr_router)
app.include_router(triage_sessions_router)
app.include_router(lab_chat_router)
app.include_router(clinical_assist_router)
app.include_router(speech_router)
app.include_router(auscultation_router)
app.include_router(treatment_plan_router)
app.include_router(all_labs_router)
app.include_router(soap_router)



@app.on_event("startup")
async def _startup():
    # Create triage_sessions table
    from infrastructure.database.session import engine, Base
    import infrastructure.database.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Connect triage event publisher (RabbitMQ)
    from infrastructure.publishers import get_triage_event_publisher
    publisher = get_triage_event_publisher()
    await publisher.connect()


@app.on_event("shutdown")
async def _shutdown():
    from infrastructure.publishers import get_triage_event_publisher
    publisher = get_triage_event_publisher()
    await publisher.close()

    from infrastructure.llm.gemini_text_client import GeminiTextClient
    await GeminiTextClient.aclose()


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "service": "ai_service"}


@app.get("/health/rag", tags=["Health"])
async def rag_health():
    """Report RAG subsystem readiness: Ollama embeddings + Qdrant collection."""
    from infrastructure.config import get_settings
    import httpx

    s = get_settings()
    if not s.RAG_ENABLED:
        return {"status": "disabled", "rag": False, "detail": "RAG_ENABLED=false"}

    results: dict = {"ollama": None, "qdrant": None, "collection": s.QDRANT_COLLECTION}

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{s.OLLAMA_URL}/api/tags")
            results["ollama"] = r.status_code == 200
    except Exception as e:
        results["ollama"] = {"error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{s.QDRANT_URL}/collections/{s.QDRANT_COLLECTION}",
                params={"timeout": 5000},
            )
            if r.status_code == 200:
                info = r.json().get("result", {})
                points = info.get("vectors_count", 0)
                results["qdrant"] = {"ready": True, "vectors_indexed": points}
            else:
                results["qdrant"] = {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        results["qdrant"] = {"error": str(e)}

    all_ok = (
        isinstance(results["ollama"], bool)
        and results["ollama"]
        and isinstance(results["qdrant"], dict)
        and results["qdrant"].get("ready")
    )
    return {
        "status": "ok" if all_ok else "degraded",
        "rag": all_ok,
        **results,
    }
