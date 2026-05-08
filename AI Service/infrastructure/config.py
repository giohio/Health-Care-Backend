from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    GROQ_API_KEY:          str
    GEMINI_API_KEY:        str
    WOKU_API_KEY:          str = ""
    WOKU_BASE_URL:         str = "https://llm.wokushop.com/v1"
    WOKU_MODEL:            str = "gemini-3-pro-preview"   # default / fallback
    # Per-use-case model overrides — override in .env to swap models without code changes.
    # Leave blank ("") to use WOKU_MODEL for that use case.
    WOKU_MODEL_TRIAGE:     str = "gemini-3-pro-preview"  # symptom-check agent (tool-calling)
    WOKU_MODEL_CLINICAL:   str = "gemini-3-pro-preview"  # doctor clinical-assist chat
    WOKU_MODEL_LAB_CHAT:   str = "gemini-3-pro-preview"  # patient lab Q&A
    WOKU_MODEL_EMR:        str = "gemini-3-pro-preview"  # EMR summary + SOAP draft
    WOKU_MODEL_FAST:       str = "gemini-3-pro-preview"  # lab suggestion, treatment plan (lighter tasks)
    GROQ_TEXT_MODEL:       str = "llama-3.3-70b-versatile"
    GEMINI_TEXT_MODEL:     str = "gemma-4-31b-it"
    GEMINI_VISION_MODEL:   str = "gemini-3-pro-preview"

    # Internal service URLs
    CLINICAL_SERVICE_URL:     str = "http://clinical_service:8000"
    PATIENT_SERVICE_URL:      str = "http://patient_service:8000"
    EMR_RESULT_SERVICE_URL:   str = "http://emr_result_service:8000"
    APPOINTMENT_SERVICE_URL:  str = "http://appointment_service:8000"
    DOCTOR_SERVICE_URL:       str = "http://doctor_service:8000"

    # Database
    DATABASE_URL:          str = "postgresql+asyncpg://postgres:postgres@localhost:5432/triage_session_db"

    # Celery / Redis
    REDIS_URL:             str = "redis://redis:6379/0"

    # RabbitMQ (for publishing triage events)
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"

    # Timeouts (seconds)
    LLM_TIMEOUT_S:         int = 120
    INTERNAL_HTTP_TIMEOUT: int = 10

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    # RAG / Qdrant
    RAG_ENABLED:       bool = False
    QDRANT_URL:        str  = "http://qdrant:6333"
    QDRANT_COLLECTION: str  = "clinical_guidelines"
    OLLAMA_URL:        str  = "http://ollama:11434"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
