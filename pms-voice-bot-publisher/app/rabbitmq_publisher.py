"""
Thin wrapper around pika for publishing maintenance_call_requested events.

- Declares a durable topic exchange + durable queue + binding (idempotent,
  safe to run every time; RabbitMQ no-ops if they already exist with the
  same properties).
- Publishes messages as persistent (delivery_mode=2) so they survive a
  broker restart while sitting in the queue.
- Uses publisher confirms so we only mark a row PUBLISHED in the DB after
  RabbitMQ has actually acknowledged the message.
"""
import json
import logging

import pika
from pika.exceptions import AMQPError, UnroutableError

from app.config import config

logger = logging.getLogger("publisher.rabbitmq")


class RabbitMQPublisher:
    def __init__(self):
        self._connection = None
        self._channel = None

    def connect(self):
        params = pika.URLParameters(config.RABBITMQ_URL)
        params.heartbeat = 30
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        self._channel.exchange_declare(
            exchange=config.RABBITMQ_EXCHANGE,
            exchange_type=config.RABBITMQ_EXCHANGE_TYPE,
            durable=True,
        )
        self._channel.queue_declare(
            queue=config.RABBITMQ_QUEUE,
            durable=True,
        )
        self._channel.queue_bind(
            queue=config.RABBITMQ_QUEUE,
            exchange=config.RABBITMQ_EXCHANGE,
            routing_key=config.RABBITMQ_ROUTING_KEY,
        )

        if config.RABBITMQ_PUBLISH_CONFIRM:
            self._channel.confirm_delivery()

        logger.info(
            "Connected to RabbitMQ. exchange=%s queue=%s routing_key=%s",
            config.RABBITMQ_EXCHANGE, config.RABBITMQ_QUEUE, config.RABBITMQ_ROUTING_KEY,
        )

    def is_open(self) -> bool:
        return bool(self._connection and self._connection.is_open)

    def publish(self, message: dict) -> None:
        if not self.is_open():
            self.connect()

        body = json.dumps(message).encode("utf-8")
        try:
            self._channel.basic_publish(
                exchange=config.RABBITMQ_EXCHANGE,
                routing_key=config.RABBITMQ_ROUTING_KEY,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                    correlation_id=message.get("correlation_id"),
                ),
                mandatory=True,
            )
        except UnroutableError as exc:
            raise RuntimeError(f"Message unroutable/not confirmed by broker: {exc}") from exc
        except AMQPError:
            # connection may have dropped; force a reconnect on next call
            self.close()
            raise

    def close(self):
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        finally:
            self._connection = None
            self._channel = None
