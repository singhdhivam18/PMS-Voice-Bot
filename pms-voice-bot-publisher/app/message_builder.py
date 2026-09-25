"""
Builds the outbound event payload published to RabbitMQ.
"""
import uuid

#from app.db import build_idempotency_key

EVENT_NAME = "maintenance_call_requested"
EVENT_VERSION = 1


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def build_message(row: dict, correlation_id: str) -> dict:
    due_date = row["due_maintenance_date"]
    due_date_str = due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date)

    return {
        "event": EVENT_NAME,
        "version": EVENT_VERSION,
        "correlation_id": correlation_id,
        "data": {
            "service_id": row["service_id"],
            "registration_no": row["registration_no"],
            "driver_name": row["driver_name"],
            "driver_phone": row["driver_phone"],
            "due_maintenance_date": due_date_str,
            "maintenance_type": row["maintenance_type"],
            "preferred_language": row["preferred_language"],
        },
    }
