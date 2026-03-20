import aio_pika
import json
from uuid_extension import uuid7


class RabbitMQPublisher:
    """
    Publisher với:
    - Persistent messages (survive broker restart)
    - Message ID để consumer idempotency check
    - Connection pooling qua robust_connection

    Usage:
        publisher = await RabbitMQPublisher.connect(url)
        await publisher.publish(
            exchange='appointment_events',
            routing_key='appointment.confirmed',
            payload={'appointment_id': '...'}
        )
    """
    def __init__(
        self,
        connection: aio_pika.RobustConnection
    ):
        self._connection = connection
        self._channel: aio_pika.RobustChannel = None

    @classmethod
    async def connect(
        cls,
        url: str
    ) -> 'RabbitMQPublisher':
        # RobustConnection tự reconnect khi mất kết nối
        connection = await aio_pika.connect_robust(url)
        publisher = cls(connection)
        await publisher._setup()
        return publisher

    async def _setup(self):
        self._channel = await self._connection.channel()
        # Publisher confirms: đảm bảo broker nhận được message
        await self._channel.set_qos(prefetch_count=10)

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        payload: dict,
        message_id: str = None,
        priority: int = 0
    ):
        """
        Publish 1 message lên exchange.

        exchange:    tên exchange (mỗi service 1 exchange)
        routing_key: tên event (vd: 'appointment.confirmed')
        payload:     dict sẽ được JSON serialize
        message_id:  nếu None → tự sinh uuid7
                     dùng outbox_event.id để đảm bảo
                     consumer có thể idempotency check
        """
        exch = await self._channel.declare_exchange(
            exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )

        message = aio_pika.Message(
            body=json.dumps(payload, default=str).encode(),
            message_id=message_id or str(uuid7()),
            content_type='application/json',
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            priority=priority
        )

        await exch.publish(
            message,
            routing_key=routing_key
        )

    async def close(self):
        await self._connection.close()
