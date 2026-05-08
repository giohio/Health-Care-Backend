from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clinical_db"
    PATIENT_SERVICE_URL: str = "http://patient-service:8001"  # nosonar
    REDIS_URL: str = "redis://localhost:6379/2"
    SQL_ECHO: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
