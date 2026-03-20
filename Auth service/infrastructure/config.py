from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    AUTH_SERVICE_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["*"]
    DEBUG: bool = True

    model_config = SettingsConfigDict(
        env_file=env_path,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
