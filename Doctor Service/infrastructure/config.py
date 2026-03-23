from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/doctor_db"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
