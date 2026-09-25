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
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


class Config:
    # ---------------- PostgreSQL ----------------
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "dev-voice-db")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_DRIVER = os.getenv("DB_DRIVER", "PostgreSQL Unicode(x64)")
    DB_CONN_TIMEOUT = int(os.getenv("DB_CONN_TIMEOUT", "10"))

    # ---------------- RabbitMQ ----------------
    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")
    RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "car_service_events")
    RABBITMQ_EXCHANGE_TYPE = os.getenv("RABBITMQ_EXCHANGE_TYPE", "topic")
    RABBITMQ_ROUTING_KEY = os.getenv("RABBITMQ_ROUTING_KEY", "maintenance.call.requested")
    RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "maintenance_call_requested_queue")
    RABBITMQ_PUBLISH_CONFIRM = _get_bool("RABBITMQ_PUBLISH_CONFIRM", True)

    # ---------------- Business rules ----------------
    # QUERY_MODE:
    #   "window" -> due_maintenance_date BETWEEN today AND today+LEAD_DAYS   (default)
    #   "exact"  -> due_maintenance_date = today+LEAD_DAYS
    #   "asis"   -> literal query supplied by the business (due_maintenance_date >= today, no upper bound)
    QUERY_MODE = os.getenv("QUERY_MODE", "window")
    LEAD_DAYS = int(os.getenv("LEAD_DAYS", "2"))

    # ---------------- Scheduling ---------------S-
    # RUN_MODE:
    #   "loop" -> stays alive, runs on an interval (good for docker-compose / always-on worker)
    #   "once" -> runs a single pass and exits 0 (good for an external cron / Kubernetes CronJob)
    RUN_MODE = os.getenv("RUN_MODE", "loop")
    SCHEDULE_INTERVAL_MINUTES = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60"))
    RUN_IMMEDIATELY_ON_START = _get_bool("RUN_IMMEDIATELY_ON_START", True)

    # ---------------- Health check ----------------
    HEALTH_CHECK_ENABLED = _get_bool("HEALTH_CHECK_ENABLED", True)
    HEALTH_CHECK_PORT = int(os.getenv("HEALTH_CHECK_PORT", "8080"))

    # ---------------- Logging ----------------
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @property
    def db_connection_string(self) -> str:
        return (
            f"DRIVER={{{self.DB_DRIVER}}};"
            f"SERVER={self.DB_HOST};"
            f"PORT={self.DB_PORT};"
            f"DATABASE={self.DB_NAME};"
            f"UID={self.DB_USER};"
            f"PWD={self.DB_PASSWORD};"
            f"Connection Timeout={self.DB_CONN_TIMEOUT};"
        )


config = Config()
