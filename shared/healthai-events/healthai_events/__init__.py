import asyncio
import json
from typing import Awaitable, Callable

import aio_pika
from healthai_events.consumer import BaseConsumer as AdvancedBaseConsumer
from healthai_events.exceptions import NonRetryableError, RetryableError
from healthai_events.publisher import RabbitMQPublisher
from healthai_events.relay import OutboxRelay


class BasePublisher:
    """Compatibility publisher used by existing microservices."""

    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url

    async def publish(self, exchange_name: str = None, routing_key: str = None, message: dict = None, **kwargs):
        exchange = exchange_name or kwargs.get("exchange")
        payload = message if message is not None else kwargs.get("payload")
        if exchange is None or routing_key is None or payload is None:
            raise ValueError("exchange/exchange_name, routing_key and message/payload are required")

        connection = await aio_pika.connect_robust(self._amqp_url)
        try:
            channel = await connection.channel()
            exch = await channel.declare_exchange(exchange, aio_pika.ExchangeType.TOPIC, durable=True)
            msg = aio_pika.Message(
                body=json.dumps(payload, default=str).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await exch.publish(msg, routing_key=routing_key)
        finally:
            await connection.close()


class BaseConsumer:
    """Compatibility consumer used by existing microservices."""

    def __init__(self, amqp_url: str, queue_name: str, exchange_name: str, routing_key: str):
        self._amqp_url = amqp_url
        self._queue_name = queue_name
        self._exchange_name = exchange_name
        self._routing_key = routing_key

    async def start(self, handler_callback: Callable[[dict], Awaitable[None]]):
        connection = await aio_pika.connect_robust(self._amqp_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(self._queue_name, durable=True)
        await queue.bind(exchange, self._routing_key)

        async def on_message(msg: aio_pika.IncomingMessage):
            async with msg.process():
                payload = json.loads(msg.body)
                await handler_callback(payload)

        await queue.consume(on_message)
        await asyncio.Future()


__all__ = [
    "BasePublisher",
    "BaseConsumer",
    "AdvancedBaseConsumer",
    "RabbitMQPublisher",
    "OutboxRelay",
    "RetryableError",
    "NonRetryableError",
]
