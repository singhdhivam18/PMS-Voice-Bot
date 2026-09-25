"""
The actual unit of work: one pass over "services due for maintenance".
"""
import logging

from app import db
from app.config import config
from app.message_builder import build_message, new_correlation_id
from app.rabbitmq_publisher import RabbitMQPublisher

logger = logging.getLogger("publisher.job")


def run_once(publisher: RabbitMQPublisher) -> dict:
    """
    Runs a single publish pass.
    Returns a small summary dict for logging/health purposes.
    Never raises for per-row problems -- a bad row is logged and skipped so
    one bad record can't block the rest of the batch.
    """
    summary = {"fetched": 0, "published": 0, "skipped_duplicate": 0, "failed": 0}
    logger.info("Starting publish run: connecting to database")
    conn = db.get_connection()
    logger.info("Database connection established")
    try:
        logger.info("Fetching due services from database")
        rows = db.fetch_due_services(conn)
        logger.info("Fetched %d due service record(s) [mode=%s, lead_days=%d]",
            len(rows), config.QUERY_MODE, config.LEAD_DAYS)
        summary["fetched"] = len(rows)
        logger.info("Fetched %d due service record(s) [mode=%s, lead_days=%d]",
                    len(rows), config.QUERY_MODE, config.LEAD_DAYS)

        for row in rows:
            service_id = db.get_service_id(row)
            correlation_id = new_correlation_id()

            try:
                should_publish = db.claim_for_publish(conn, service_id, correlation_id, row)
            except Exception:
                logger.exception("correlation_id claim failed for key=%s", correlation_id)
                summary["failed"] += 1
                continue

            if not should_publish:
                summary["skipped_duplicate"] += 1
                continue

            message = build_message(row, correlation_id)

            try:
                publisher.publish(message)
                db.mark_published(conn, service_id)
                summary["published"] += 1
                logger.info(
                    "Published event correlation_id=%s  registration_no=%s",
                    correlation_id, row["registration_no"],
                )
            except Exception as exc:
                logger.exception("Publish failed for key=%s", correlation_id)
                try:
                    db.mark_failed(conn, service_id,str(exc))
                except Exception:
                    logger.exception("Also failed to record FAILED status for key=%s", correlation_id)
                summary["failed"] += 1

    finally:
        conn.close()

    logger.info("Run summary: %s", summary)
    return summary
