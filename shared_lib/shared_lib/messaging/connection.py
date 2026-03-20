import aio_pika
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class RabbitMQConnection:
    _connections: Dict[str, aio_pika.RobustConnection] = {}
    _channels: Dict[str, aio_pika.RobustChannel] = {}

    @classmethod
    async def get_connection(cls, amqp_url: str) -> aio_pika.RobustConnection:
        if amqp_url not in cls._connections or cls._connections[amqp_url].is_closed:
            logger.info(f"Connecting to RabbitMQ: {amqp_url}")
            cls._connections[amqp_url] = await aio_pika.connect_robust(amqp_url)
        return cls._connections[amqp_url]

    @classmethod
    async def get_channel(cls, amqp_url: str) -> aio_pika.RobustChannel:
        if amqp_url not in cls._channels or cls._channels[amqp_url].is_closed:
            connection = await cls.get_connection(amqp_url)
            cls._channels[amqp_url] = await connection.channel()
            logger.info("RabbitMQ Channel created")
        return cls._channels[amqp_url]
