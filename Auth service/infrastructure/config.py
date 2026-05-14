from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    REDIS_URL: str = "redis://localhost:6379/0"
    AUTH_SERVICE_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["*"]
    DEBUG: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    model_config = SettingsConfigDict(env_file=env_path, env_file_encoding="utf-8", case_sensitive=True, extra="ignore")


settings = Settings()
