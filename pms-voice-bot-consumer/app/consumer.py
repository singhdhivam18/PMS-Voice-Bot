import json
import logging

import pika

from app import db
from app.config import config
from app.voice_agent import voice_agent

logger = logging.getLogger("consumer.rabbitmq")


def _build_call_event_message(result: dict, correlation_id: str) -> str:
    """Create the event message without storing an unbounded API response."""
    conversation_id = result.get("conversation_id")
    provider_call_id = result.get("call_id") or result.get("provider_call_id")

    details = {
        "correlation_id": correlation_id,
        "status": result.get("status"),
    }

    if conversation_id:
        details["conversation_id"] = conversation_id
    if provider_call_id:
        details["provider_call_id"] = provider_call_id

    return json.dumps(details, ensure_ascii=False, separators=(",", ":"))


def consume():
    logger.info("Connecting to RabbitMQ...")

    parameters = pika.URLParameters(config.RABBITMQ_URL)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(
        exchange=config.RABBITMQ_EXCHANGE,
        exchange_type=config.RABBITMQ_EXCHANGE_TYPE,
        durable=True,
    )

    channel.queue_declare(
        queue=config.RABBITMQ_QUEUE,
        durable=True,
    )

    channel.queue_bind(
        exchange=config.RABBITMQ_EXCHANGE,
        queue=config.RABBITMQ_QUEUE,
        routing_key=config.RABBITMQ_ROUTING_KEY,
    )

    channel.basic_qos(prefetch_count=1)

    def callback(ch, method, properties, body):
        conn = None

        try:
            message = json.loads(body.decode("utf-8"))

            event_name = message.get("event")
            version = message.get("version")
            correlation_id = message["correlation_id"]
            data = message["data"]

            if not isinstance(data, dict):
                raise ValueError("Message 'data' must be an object")

            service_id = int(data["service_id"])
            registration_no = data["registration_no"]
            driver_name = data["driver_name"]
            driver_phone = data["driver_phone"]
            due_maintenance_date = data["due_maintenance_date"]
            maintenance_type = data["maintenance_type"]
            preferred_language=data["preferred_language"]
            event_id=data["event_id"]
            logger.info(
                "Received RabbitMQ message event=%s version=%s "
                "correlation_id=%s service_id=%s",
                event_name,
                version,
                correlation_id,
                service_id,
            )

            # Existing job is created elsewhere. This worker only resolves it.
            conn = db.get_connection()
            job = db.get_job_by_service_id(conn, service_id)
            conn.close()
            conn = None

            if job is None:
                raise RuntimeError(
                    f"No voice_bot_call_job found for service_id={service_id}"
                )

            job_id = int(job["id"])
            logger.info(
                "Resolved existing voice_bot_call_job job_id=%s service_id=%s",
                job_id,
                service_id,
            )

            # The HTTP call must succeed before we write CALL_INITIATED.
            result = voice_agent.trigger_call(
                correlation_id=correlation_id,
                service_id=service_id,
                registration_no=registration_no,
                driver_name=driver_name,
                driver_phone=driver_phone,
                due_maintenance_date=due_maintenance_date,
                maintenance_type=maintenance_type,
                preferred_language=preferred_language,
            )

            # Persist the event only after the voice API confirms initiation.
            conn = db.get_connection()
            db.insert_call_initiated_event(
                conn,
                event_id=event_id,
                system_message=_build_call_event_message(
                    result,
                    correlation_id,
                ),
            )
            conn.close()
            conn = None

            # ACK only after call initiation + event commit succeed.
            ch.basic_ack(delivery_tag=method.delivery_tag)

            logger.info(
                "RabbitMQ message ACKed job_id=%s correlation_id=%s",
                job_id,
                correlation_id,
            )

        except Exception:
            logger.exception("Failed processing RabbitMQ message")

            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            # Preserve the existing manual-ACK/requeue behavior.
            ch.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=True,
            )

    channel.basic_consume(
        queue=config.RABBITMQ_QUEUE,
        on_message_callback=callback,
        auto_ack=False,
    )

    logger.info(
        "Consumer listening on queue=%s",
        config.RABBITMQ_QUEUE,
    )

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    finally:
        if not connection.is_closed:
            connection.close()
        logger.info("RabbitMQ connection closed")
