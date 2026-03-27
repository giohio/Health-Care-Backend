import json
import os
import aio_pika
from uuid_extension import uuid7

async def publish_event(exchange: str, routing_key: str, payload: dict):
    """Publish a raw event to RabbitMQ for testing integration consumers."""
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    connection = await aio_pika.connect_robust(rabbitmq_url)
    try:
        async with connection:
            channel = await connection.channel()
            exch = await channel.declare_exchange(exchange, aio_pika.ExchangeType.TOPIC, durable=True)
            
            message = aio_pika.Message(
                body=json.dumps(payload, default=str).encode(),
                message_id=str(uuid7()),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            
            await exch.publish(message, routing_key=routing_key)
    finally:
        await connection.close()
