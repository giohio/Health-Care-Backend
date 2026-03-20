import aio_pika
import json
import logging
from abc import ABC, abstractmethod
from healthai_cache import CacheClient
from .exceptions import RetryableError, NonRetryableError

logger = logging.getLogger(__name__)


class BaseConsumer(ABC):
    """
    Base class cho tất cả RabbitMQ consumers.

    Có sẵn:
    1. Idempotency check via message_id
       → Không xử lý duplicate messages
    2. Retry với exponential backoff
       → Tự động retry khi gặp RetryableError
    3. DLQ routing khi max retries exceeded
       → Không mất message, có thể replay sau

    Cách viết consumer mới:
        class AppointmentConfirmedConsumer(BaseConsumer):
            QUEUE = 'notification.appointment_confirmed'
            EXCHANGE = 'appointment_events'
            ROUTING_KEY = 'appointment.confirmed'

            async def handle(self, payload: dict):
                await self.notification_service.create(
                    user_id=payload['patient_id'],
                    title='Appointment Confirmed',
                    body=f"Your appointment is confirmed"
                )
    """
    QUEUE: str            # Tên queue
    EXCHANGE: str         # Exchange subscribe vào
    ROUTING_KEY: str      # Pattern routing key
    MAX_RETRIES: int = 5
    RETRY_DELAYS: list = [1, 5, 15, 60, 300]
    IDEMPOTENCY_TTL: int = 86400  # 24h

    def __init__(
        self,
        connection: aio_pika.RobustConnection,
        cache: CacheClient
    ):
        self._connection = connection
        self._cache = cache
        self._channel = None

    async def start(self):
        """Bắt đầu consume messages."""
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        # Declare exchange
        exchange = await self._channel.declare_exchange(
            self.EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )

        # Declare queue với DLQ config
        queue = await self._channel.declare_queue(
            self.QUEUE,
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'dlq_exchange',
                'x-dead-letter-routing-key':
                    f'dlq.{self.QUEUE}',
                'x-message-ttl': 86400000,  # 24h
            }
        )

        # Bind queue → exchange
        await queue.bind(exchange, self.ROUTING_KEY)

        # Start consuming
        await queue.consume(self._process)
        logger.info(f"{self.__class__.__name__} started")

    async def _process(
        self,
        message: aio_pika.IncomingMessage
    ):
        async with message.process(ignore_processed=True):
            msg_id = message.message_id
            retry_count = int(
                (message.headers or {}).get(
                    'x-retry-count', 0
                )
            )

            # ── Idempotency check ──
            if msg_id:
                idem_key = f"processed_msg:{msg_id}"
                already_done = await self._cache.get(
                    idem_key
                )
                if already_done:
                    logger.debug(
                        f"Skipping duplicate msg {msg_id}"
                    )
                    return  # auto-ack khi exit context

            # ── Process message ──
            try:
                payload = json.loads(message.body)
                await self.handle(payload)

                # Mark processed
                if msg_id:
                    await self._cache.set(
                        f"processed_msg:{msg_id}",
                        True,
                        ttl=self.IDEMPOTENCY_TTL
                    )

            except NonRetryableError as e:
                logger.error(
                    f"{self.__class__.__name__} "
                    f"non-retryable error: {e}"
                )
                raise  # nack + DLQ

            except RetryableError as e:
                if retry_count < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[
                        min(retry_count,
                            len(self.RETRY_DELAYS) - 1)
                    ]
                    logger.warning(
                        f"{self.__class__.__name__} retry "
                        f"#{retry_count + 1}/{self.MAX_RETRIES} "
                        f"in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    raise  # nack to retry
                else:
                    logger.error(
                        f"{self.__class__.__name__} "
                        f"max retries exceeded: {e}"
                    )
                    raise

            except Exception as e:
                # Unexpected error → treat as retryable
                if retry_count < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[
                        min(retry_count,
                            len(self.RETRY_DELAYS) - 1)
                    ]
                    logger.warning(
                        f"{self.__class__.__name__} "
                        f"unexpected error, retry in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    raise
                else:
                    logger.error(
                        f"{self.__class__.__name__} "
                        f"max retries exceeded (unexpected): {e}"
                    )
                    raise

    @abstractmethod
    async def handle(self, payload: dict):
        """Override trong subclass."""
        raise NotImplementedError


import asyncio
