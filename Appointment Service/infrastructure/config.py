from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/appointment_db"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    DOCTOR_SERVICE_URL: str = "http://doctor-service:8002"  # nosonar
    REDIS_URL: str = "redis://localhost:6379/0"
    DEFAULT_APPOINTMENT_AMOUNT_VND: int = 500000
    SQL_ECHO: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
