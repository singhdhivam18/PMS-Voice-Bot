import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    DB_SERVER = os.getenv("DB_SERVER", "localhost")
    DB_PORT = os.getenv("DB_PORT", "1433")
    DB_NAME = os.getenv("DB_NAME", "car-voice-db")
    DB_USER = os.getenv("DB_USER", "sa")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_DRIVER = os.getenv(
        "DB_DRIVER",
        "ODBC Driver 17 for SQL Server",
    )
    DB_ENCRYPT = os.getenv("DB_ENCRYPT", "yes")
    DB_TRUST_SERVER_CERTIFICATE = os.getenv(
        "DB_TRUST_SERVER_CERTIFICATE",
        "yes",
    )
    DB_CONN_TIMEOUT = int(os.getenv("DB_CONN_TIMEOUT", "10"))

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
    RABBITMQ_QUEUE = os.getenv(
        "RABBITMQ_QUEUE",
        "maintenance_call_requested_queue",
    )
    RABBITMQ_ROUTING_KEY = os.getenv(
        "RABBITMQ_ROUTING_KEY",
        "maintenance.call.requested",
    )
    VOICE_AGENT_BASE_URL = os.getenv(
        "VOICE_AGENT_BASE_URL",
        "http://localhost:8000",
    )
    VOICE_AGENT_DEPOT_NAME = os.getenv(
    "VOICE_AGENT_DEPOT_NAME",
    "Bangalore Central Depot",
    )

    VOICE_AGENT_CALLBACK_URL = os.getenv(
        "VOICE_AGENT_CALLBACK_URL",
        "",
    )

    VOICE_AGENT_TIMEOUT = float(
        os.getenv("VOICE_AGENT_TIMEOUT", "330")
    )
    HEALTH_CHECK_ENABLED = (
        os.getenv("HEALTH_CHECK_ENABLED", "true")
        .strip()
        .lower()
        in {"1", "true", "yes", "y", "on"}
    )

    HEALTH_CHECK_PORT = int(
        os.getenv("HEALTH_CHECK_PORT", "8081")
    )

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @property
    def db_connection_string(self) -> str:
        return (
            f"DRIVER={{{self.DB_DRIVER}}};"
            f"SERVER={self.DB_SERVER},{self.DB_PORT};"
            f"DATABASE={self.DB_NAME};"
            f"UID={self.DB_USER};"
            f"PWD={self.DB_PASSWORD};"
            f"Encrypt={self.DB_ENCRYPT};"
            f"TrustServerCertificate="
            f"{self.DB_TRUST_SERVER_CERTIFICATE};"
            f"Connection Timeout={self.DB_CONN_TIMEOUT};"
        )


config = Config()