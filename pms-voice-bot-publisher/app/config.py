"""
Central configuration for the Publisher Worker.

Everything is driven by environment variables so the same image can run
in dev / staging / prod, and inside docker-compose, without code changes.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)

    if val is None:
        return default

    return val.strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )


class Config:
    # ---------------- PostgreSQL ----------------
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "dev-voice-db")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "Test@123")
    DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

    # ---------------- RabbitMQ ----------------
    RABBITMQ_URL = os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@localhost:5672/%2F",
    )

    RABBITMQ_EXCHANGE = os.getenv(
        "RABBITMQ_EXCHANGE",
        "car_service_events",
    )

    RABBITMQ_EXCHANGE_TYPE = os.getenv(
        "RABBITMQ_EXCHANGE_TYPE",
        "topic",
    )

    RABBITMQ_ROUTING_KEY = os.getenv(
        "RABBITMQ_ROUTING_KEY",
        "maintenance.call.requested",
    )

    RABBITMQ_QUEUE = os.getenv(
        "RABBITMQ_QUEUE",
        "maintenance_call_requested_queue",
    )

    RABBITMQ_PUBLISH_CONFIRM = _get_bool(
        "RABBITMQ_PUBLISH_CONFIRM",
        True,
    )

    # ---------------- Business rules ----------------
    #
    # QUERY_MODE:
    #   "window" -> today through today + LEAD_DAYS
    #   "exact"  -> exactly today + LEAD_DAYS
    #   "asis"   -> today or later, no upper bound
    #
    QUERY_MODE = os.getenv("QUERY_MODE", "window")

    LEAD_DAYS = int(
        os.getenv("LEAD_DAYS", "2")
    )

    # ---------------- Scheduling ----------------
    #
    # RUN_MODE:
    #   "loop" -> continuously run
    #   "once" -> single execution and exit
    #
    RUN_MODE = os.getenv("RUN_MODE", "loop")

    SCHEDULE_INTERVAL_MINUTES = int(
        os.getenv("SCHEDULE_INTERVAL_MINUTES", "60")
    )

    RUN_IMMEDIATELY_ON_START = _get_bool(
        "RUN_IMMEDIATELY_ON_START",
        True,
    )

    # ---------------- Health check ----------------

    HEALTH_CHECK_ENABLED = _get_bool(
        "HEALTH_CHECK_ENABLED",
        True,
    )

    HEALTH_CHECK_PORT = int(
        os.getenv("HEALTH_CHECK_PORT", "8080")
    )

    # ---------------- Logging ----------------

    LOG_LEVEL = os.getenv(
        "LOG_LEVEL",
        "INFO",
    )


config = Config()