import json
import logging

import pika

from app.config import config
from app import db
from app.voice_agent import voice_agent

logger = logging.getLogger("consumer.rabbitmq")


def consume():
    logger.info("Connecting to RabbitMQ...")

    parameters = pika.URLParameters(config.RABBITMQ_URL)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # ---------------------------------------------------------
    # RabbitMQ topology
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Message callback
    # ---------------------------------------------------------
    def callback(ch, method, properties, body):
        conn = None

        try:
            message = json.loads(body.decode("utf-8"))

            correlation_id = message["correlation_id"]
            idempotency_key = message["idempotency_key"]
            data = message["data"]

            service_id = data["service_id"]
            carno = data["carno"]
            driver_name = data["driver_name"]
            driver_phone = data["driver_phone"]
            due_maintenance_date = data["due_maintenance_date"]
            maintenance_type = data["maintenance_type"]

            logger.info(
                "Received message "
                "correlation_id=%s idempotency_key=%s",
                correlation_id,
                idempotency_key,
            )

           # -------------------------------------------------
            # 1. Check whether job already exists
            # -------------------------------------------------
            conn = db.get_connection()

            existing_job = db.get_job_by_idempotency_key(
                conn,
                idempotency_key,
            )

            if existing_job:
                logger.info(
                    "Existing VoiceCallJob found "
                    "job_id=%s job_status=%s call_status=%s "
                    "correlation_id=%s",
                    existing_job.job_id,
                    existing_job.job_status,
                    existing_job.call_status,
                    existing_job.correlation_id,
                )

                existing_status = str(
                    existing_job.job_status or ""
                ).upper()

                existing_call_status = str(
                    existing_job.call_status or ""
                ).upper()

                # Already fully completed → safe duplicate ACK.
                if (
                    existing_status == "COMPLETED"
                    and existing_call_status == "COMPLETED"
                ):
                    conn.rollback()
                    conn.close()
                    conn = None

                    ch.basic_ack(
                        delivery_tag=method.delivery_tag
                    )

                    logger.info(
                        "Duplicate completed job ACKed "
                        "job_id=%s idempotency_key=%s",
                        existing_job.job_id,
                        idempotency_key,
                    )

                    return

                # Incomplete job → reuse this job and continue processing.
                job_id = int(existing_job.job_id)

                logger.info(
                    "Resuming incomplete VoiceCallJob "
                    "job_id=%s job_status=%s call_status=%s",
                    job_id,
                    existing_status,
                    existing_call_status,
                )

                conn.rollback()
                conn.close()
                conn = None

            else:
                # -------------------------------------------------
                # 2. Create a new VoiceCallJob
                # -------------------------------------------------
                job_id = db.create_job(
                    conn,
                    service_id=service_id,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )

                conn.close()
                conn = None


            # -------------------------------------------------
            # 3. Call FastAPI Voice Agent POC
            # -------------------------------------------------
            logger.info(
                "Calling Voice Agent "
                "job_id=%s correlation_id=%s",
                job_id,
                correlation_id,
            )

            result = voice_agent.trigger_call(
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                service_id=service_id,
                carno=carno,
                driver_name=driver_name,
                driver_phone=driver_phone,
                due_maintenance_date=due_maintenance_date,
                maintenance_type=maintenance_type,
            )

            logger.info(
                "Voice Agent POC call intated"
                "job_id=%s correlation_id=%s",
                job_id,
                correlation_id,
            )

            # -------------------------------------------------
            # 4. Update VoiceCallJobs
            # -------------------------------------------------
            conn = db.get_connection()

            try:
                db.mark_call_initiated(
                    conn,
                    job_id=job_id,
                    result=result,
                )
            finally:
                conn.close()
                conn = None

            # -------------------------------------------------
            # 5. ACK ONLY after DB COMMIT
            # -------------------------------------------------
            ch.basic_ack(
                delivery_tag=method.delivery_tag
            )

            logger.info(
                "RabbitMQ message ACKed "
                "job_id=%s correlation_id=%s",
                job_id,
                correlation_id,
            )

        except Exception:
            logger.exception(
                "Failed processing RabbitMQ message"
            )

            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass

                try:
                    conn.close()
                except Exception:
                    pass

            # Do not ACK failed messages.
            # RabbitMQ will requeue them.
            ch.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=True,
            )

    # ---------------------------------------------------------
    # THIS IS CRITICAL
    # Register callback before start_consuming()
    # ---------------------------------------------------------
    channel.basic_consume(
        queue=config.RABBITMQ_QUEUE,
        on_message_callback=callback,
        auto_ack=False,
    )

    logger.info(
        "Consumer listening on queue=%s",
        config.RABBITMQ_QUEUE,
    )

    # ---------------------------------------------------------
    # Keep process alive
    # ---------------------------------------------------------
    try:
        channel.start_consuming()

    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")

    finally:
        if not connection.is_closed:
            connection.close()

        logger.info("RabbitMQ connection closed")