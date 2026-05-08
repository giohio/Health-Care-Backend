from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/emr_result_db"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    NOTIFICATION_SERVICE_URL: str = "http://notification_service:8000"  # nosonar
    CLINICAL_SERVICE_URL: str = "http://clinical_service:8000"  # nosonar
    PATIENT_SERVICE_URL: str = "http://patient_service:8000"  # nosonar
    AI_SERVICE_URL: str = "http://ai_service:8000"  # nosonar
    REDIS_URL: str = "redis://localhost:6379/3"
    SQL_ECHO: bool = False

    # File upload storage
    UPLOAD_DIR: str = "/app/uploads"
    UPLOAD_BASE_URL: str = "http://emr_result_service:8000/uploads"
    MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024  # 20 MB

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
