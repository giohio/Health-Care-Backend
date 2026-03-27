from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/patient_db"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_PUBLIC_KEY_PATH: str = "/keys/jwt_public.pem"

    DEBUG: bool = False


settings = Settings()
