import json
import pika

from app.config import config


message = {
    "event": "maintenance_call_requested",
    "version": 1,
    "correlation_id": "a24de977-ac9c-4c68-8891-7e5529b39519",
    "idempotency_key": "4:2026-09-11:REGULAR",
    "data": {
        "service_id": 4,
        "carno": "KA09GH3456",
        "driver_name": "Vijay Rao",
        "driver_phone": "919811223344",
        "due_maintenance_date": "2026-09-11",
        "maintenance_type": "REGULAR"
    }
}


connection = pika.BlockingConnection(
    pika.URLParameters(config.RABBITMQ_URL)
)

channel = connection.channel()

channel.basic_publish(
    exchange=config.RABBITMQ_EXCHANGE,
    routing_key=config.RABBITMQ_ROUTING_KEY,
    body=json.dumps(message).encode("utf-8"),
    properties=pika.BasicProperties(
        content_type="application/json"
    ),
)

print("Duplicate test message published")

connection.close()