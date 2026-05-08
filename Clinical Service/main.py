import importlib.util
import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.database import models as _db_models  # noqa: F401
from infrastructure.database.session import engine

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Clinical Service",
    description="Service for managing patient clinical records — diagnoses, medications, and clinical notes.",
    version="1.0.0",
    root_path=os.getenv("APP_ROOT_PATH", ""),
)

setup_logging("clinical-service")
setup_telemetry(app, "clinical-service", db_engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "clinical-service"}


from presentation.routes import clinical_router

app.include_router(clinical_router)
