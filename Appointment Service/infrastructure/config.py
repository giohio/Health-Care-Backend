from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/appointment_db"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    DOCTOR_SERVICE_URL: str = "http://doctor-service:8002"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
