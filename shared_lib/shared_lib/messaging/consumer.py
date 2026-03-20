import json
import logging
import asyncio
import aio_pika
from typing import Callable, Awaitable, Any, Dict
from .connection import RabbitMQConnection

logger = logging.getLogger(__name__)


class BaseConsumer:
    def __init__(self, amqp_url: str, queue_name: str, exchange_name: str, routing_key: str,
                 retry_delay: int = 5, max_retries: int = 0):
        self.amqp_url = amqp_url
        self.queue_name = queue_name
        self.exchange_name = exchange_name
        self.routing_key = routing_key
        self.retry_delay = retry_delay
        self.max_retries = max_retries  # 0 = infinite retries

    async def start(self, handler_callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """
        Starts the consumer with automatic reconnection on failure.
        """
        attempt = 0
        while True:
            try:
                attempt += 1
                logger.info(f"[Consumer] Connecting to RabbitMQ (attempt {attempt})...")
                channel = await RabbitMQConnection.get_channel(self.amqp_url)

                # Setup Dead Letter Exchange (DLX) & DLQ for failed messages
                dlx_name = f"{self.queue_name}_dlx"
                dlq_name = f"{self.queue_name}_dlq"

                await channel.declare_exchange(dlx_name, aio_pika.ExchangeType.FANOUT, durable=True)
                dlq = await channel.declare_queue(dlq_name, durable=True)
                await dlq.bind(dlx_name)

                # Setup Main Exchange & Queue with DLX configuration
                exchange = await channel.declare_exchange(
                    self.exchange_name,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True
                )

                queue = await channel.declare_queue(
                    self.queue_name,
                    durable=True,
                    arguments={"x-dead-letter-exchange": dlx_name}
                )
                await queue.bind(exchange, routing_key=self.routing_key)

                logger.info(f"[Consumer] Connected. Waiting for messages in '{self.queue_name}'")
                attempt = 0  # reset on successful connect

                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        try:
                            payload = json.loads(message.body.decode())
                            await handler_callback(payload)
                            await message.ack()
                            logger.info(f"[Consumer] Message in '{self.queue_name}' processed and ACKed")

                        except (ValueError, KeyError, TypeError) as e:
                            logger.error(f"[Consumer] Fatal error in '{self.queue_name}': {e}. Rejecting to DLQ.")
                            await message.reject(requeue=False)

                        except Exception as e:
                            logger.error(f"[Consumer] Transient error in '{self.queue_name}': {e}. NACKing for requeue.")
                            await message.nack(requeue=True)

            except Exception as e:
                logger.warning(f"[Consumer] '{self.queue_name}' connection lost: {e}. Retrying in {self.retry_delay}s...")
                if self.max_retries and attempt >= self.max_retries:
                    logger.critical(f"[Consumer] Max retries reached for '{self.queue_name}'. Giving up.")
                    raise
                await asyncio.sleep(self.retry_delay)


# For backward compatibility or service specific naming
class RabbitMQConsumer(BaseConsumer):
    pass
