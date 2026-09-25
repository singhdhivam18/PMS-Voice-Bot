# Maintenance Call Consumer Worker

This worker consumes `maintenance_call_requested` messages from RabbitMQ and drives the outbound voice-call lifecycle.

## Message contract

```json
{
  "event": "maintenance_call_requested",
  "version": 1,
  "correlation_id": "59153412-bc29-4576-8b8f-a2a9eae55cf2",
  "data": {
    "service_id": 6,
    "registration_no": "KA01AB9981",
    "driver_name": "Aman",
    "driver_phone": "+919980014906",
    "due_maintenance_date": "2026-09-26",
    "maintenance_type": "REGULAR"
  }
}
```

## Processing flow

1. Consume the RabbitMQ message with manual acknowledgement.
2. Find the existing `public.voice_bot_call_job` row using `service_id`.
3. Call the Voice Agent/FastAPI `/api/outbound-call` endpoint.
4. Require a successful `status=call_initiated` response.
5. Insert `CALL_INITIATED` into `public.voice_bot_call_job_event`.
6. Commit the event and then ACK the RabbitMQ message.
7. The later `/api/voice/callback` request is matched using `correlationId`.
8. Persist the callback JSON to `CALLBACK_PAYLOAD_DIR`.
9. Mark the latest `CALL_INITIATED` event as `COMPLETED`.
10. Update the existing `voice_bot_call_job` row:
    - `callback_received = true`
    - `callback_payload_file_path = <stored JSON path>`
    - `updated_at = CURRENT_TIMESTAMP`

There is no `VoiceCallJobs` table creation, no job creation in the consumer, and no idempotency key/table logic.

## Database

The worker expects PostgreSQL and the two tables supplied for this flow:

- `public.voice_bot_call_job`
- `public.voice_bot_call_job_event`

## RabbitMQ failure behavior

The message is ACKed only after the outbound call succeeds and the `CALL_INITIATED` event is committed. Any processing exception results in `basic_nack(..., requeue=True)`.
