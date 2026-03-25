from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Payment Service Configuration"""

    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/payment_db")

    # RabbitMQ
    RABBITMQ_URL: str = Field(default="amqp://guest:guest@localhost:5672/")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # VNPAY
    VNPAY_TMN_CODE: str = Field(default="TV1BKXSO")
    VNPAY_HASH_SECRET: str = Field(default="9W8MLHMKMYTSO7DN1JGI1H9XEQOYXPWH")
    VNPAY_URL: str = Field(default="https://sandbox.vnpayment.vn/paygate")
    VNPAY_RETURN_URL: str = Field(default="http://localhost:3000/payment-return")

    # App
    APP_ROOT_PATH: str = Field(default="/payments")

    # Telemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(default="http://localhost:4318/v1/traces")

    model_config = ConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
