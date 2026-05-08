"""DB connection URL helpers and small utilities shared by all seed modules."""
import os
from datetime import time


def _t(s: str) -> time:
    """Parse 'HH:MM:SS' → datetime.time."""
    h, m, sec = s.split(":")
    return time(int(h), int(m), int(sec))


def _auth_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/authentication"


def _doctor_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/doctor_db"


def _patient_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/patient_db"


def _appointment_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/appointment_db"


def _emr_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/emr_result_db"


def _clinical_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/clinical_db"


def _ai_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/triage_session_db"


def _payment_db_url() -> str:
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    h = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/payment_db"
