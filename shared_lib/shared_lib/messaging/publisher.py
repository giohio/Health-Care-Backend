import json
import logging
import aio_pika
from typing import Dict, Any
from .connection import RabbitMQConnection

logger = logging.getLogger(__name__)

class BasePublisher:
    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url

    async def publish(self, exchange_name: str, routing_key: str, message: Dict[str, Any], delay_ms: int = 0):
        try:
            channel = await RabbitMQConnection.get_channel(self.amqp_url)
            
            if delay_ms > 0:
                exchange = await channel.declare_exchange(
                    exchange_name,
                    type="x-delayed-message",
                    arguments={"x-delayed-type": "topic"},
                    durable=True
                )
                headers = {"x-delay": delay_ms}
            else:
                exchange = await channel.declare_exchange(
                    exchange_name, 
                    aio_pika.ExchangeType.TOPIC,
                    durable=True
                )
                headers = {}

            # Message properties
            msg = aio_pika.Message(
                body=json.dumps(message).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                headers=headers
            )

            await exchange.publish(msg, routing_key=routing_key)
            logger.info(f"Published message to {exchange_name} [{routing_key}]: {message}")
            
        except Exception as e:
            logger.error(f"Failed to publish message: {str(e)}")
            raise

# For backward compatibility or service specific naming
class RabbitMQPublisher(BasePublisher):
    pass
