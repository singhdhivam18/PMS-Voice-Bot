import logging
import signal
import sys
import time
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import config
from app.health import start_health_server, set_status
from app.job import run_once
from app.rabbitmq_publisher import RabbitMQPublisher

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("publisher.main")

publisher = RabbitMQPublisher()


def execute_job():
    logger.info("execute_job() started")
    try:
        run_once(publisher)
        set_status(ok=True, last_run=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        logger.exception("Publish run failed")
        set_status(ok=False, last_run=datetime.now(timezone.utc).isoformat(), last_error=str(exc))
        if config.RUN_MODE == "once":
            raise


def run_loop():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        execute_job,
        "interval",
        minutes=config.SCHEDULE_INTERVAL_MINUTES,
        id="publish_due_services",
        max_instances=1,
        coalesce=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received, stopping scheduler...")
        scheduler.shutdown(wait=False)
        publisher.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info(
        "Starting in LOOP mode: every %d minute(s), immediate_run=%s",
        config.SCHEDULE_INTERVAL_MINUTES,
        config.RUN_IMMEDIATELY_ON_START,
    )

    if config.RUN_IMMEDIATELY_ON_START:
        logger.info("Running first publish job immediately")
        execute_job()

    scheduler.start()

def run_once_and_exit():
    logger.info("Starting in ONCE mode: single pass then exit")
    try:
        execute_job()
    finally:
        publisher.close()


def main():
    if config.HEALTH_CHECK_ENABLED:
        start_health_server(config.HEALTH_CHECK_PORT)

    if config.RUN_MODE == "once":
        run_once_and_exit()
    else:
        run_loop()


if __name__ == "__main__":
    main()
