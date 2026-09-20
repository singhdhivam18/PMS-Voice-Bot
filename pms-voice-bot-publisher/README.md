# Publisher Worker — Maintenance Call Requests

Worker 1 in the voice-agent pipeline:

```
SQL Server (ServiceRecords + Vehicles)
        │  query due services
        ▼
Publisher Worker  ── this service ──
  - query DB
  - claim idempotency key
  - build correlation_id
  - publish to RabbitMQ
        │
        ▼
RabbitMQ (topic exchange: car_service_events)
        │
        ▼
Consumer Worker (next service — validates, updates job state, triggers ElevenLabs voice bot)
```

## What it does

1. Queries `ServiceRecords` joined to `Vehicles` for rows with
   `service_status = 'DUE'`.
2. Applies a configurable due-date window (`QUERY_MODE` / `LEAD_DAYS`,
   default = due within the next 2 days).
3. For each row, builds:
   - `idempotency_key` = `"{service_id}:{due_maintenance_date}:{maintenance_type}"`
   - `correlation_id` = a fresh UUIDv4 per publish attempt
4. Atomically "claims" the idempotency key against a SQL Server tracking
   table (`dbo.MaintenanceCallIdempotency`) — if it's already `PUBLISHED`,
   the row is skipped so the same driver never gets called twice for the
   same due service.
5. Publishes the event to RabbitMQ with publisher confirms, and only marks
   the row `PUBLISHED` in the DB after RabbitMQ has acknowledged receipt.

## Message contract

```json
{
  "event": "maintenance_call_requested",
  "version": 1,
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "idempotency_key": "1:2026-09-09:REGULAR",
  "data": {
    "service_id": 1,
    "carno": "KA01AB1234",
    "driver_name": "Raj Kumar",
    "driver_phone": "919980014906",
    "due_maintenance_date": "2026-09-09",
    "maintenance_type": "REGULAR"
  }
}
```

Published to exchange `car_service_events` (topic) with routing key
`maintenance.call.requested`, bound to durable queue
`maintenance_call_requested_queue` — this is the queue your Consumer
Worker should listen on.

## Idempotency design

A unique-keyed table means "already published" is enforced by the
database itself, not by in-memory state — so it survives worker restarts
and works even if you later run more than one replica of this service.

Row states: `PENDING` (claimed, not yet confirmed published) →
`PUBLISHED` (done, will never be re-sent) or `FAILED` (publish attempt
errored — eligible to be retried automatically on the *next* scheduled
run, since `PENDING`/`FAILED` rows are re-claimable, `PUBLISHED` rows are
not).

Run once against your existing database before first use:

```bash
sqlcmd -S <server> -d <database> -i sql/001_create_idempotency_table.sql
```

## Scheduling

Two modes, same code path, controlled by `RUN_MODE`:

- `RUN_MODE=loop` (default) — the container stays alive and fires the job
  every `SCHEDULE_INTERVAL_MINUTES` (via APScheduler), running once
  immediately on startup if `RUN_IMMEDIATELY_ON_START=true`. This is what
  `docker-compose.yml` uses.
- `RUN_MODE=once` — runs a single pass and exits (0 on success, non-zero
  on failure). Point an external cron job, Kubernetes `CronJob`, or your
  own scheduler at `docker run ... -e RUN_MODE=once <image>` if you'd
  rather own the scheduling outside the container.

## Configuration

See `.env.example` for the full list (DB connection, RabbitMQ topology,
`QUERY_MODE` / `LEAD_DAYS`, scheduling, health check, logging).

`QUERY_MODE`:
| Mode     | Behavior |
|----------|----------|
| `window` | due date is between today and today+`LEAD_DAYS` (default, `LEAD_DAYS=2`) |
| `exact`  | due date is exactly today+`LEAD_DAYS` |
| `asis`   | literal business query: due date >= today, no upper bound |

## Running locally

```bash
cp .env.example .env
# edit .env with your real DB_SERVER / DB_USER / DB_PASSWORD

docker compose up --build
```

- RabbitMQ management UI: http://localhost:15672 (guest/guest)
- Worker health check: http://localhost:8080/health

## Running a single pass without Docker (for quick DB/query testing)

```bash
pip install -r requirements.txt
export $(cat .env | xargs)   # or set vars manually
RUN_MODE=once python -m app.main
```

## Files

```
publisher-worker/
├── app/
│   ├── main.py                # entrypoint: health server + scheduler wiring
│   ├── job.py                 # one publish pass: fetch → claim → build → publish
│   ├── db.py                  # SQL Server queries + idempotency claim logic
│   ├── message_builder.py     # builds the event payload + correlation_id
│   ├── rabbitmq_publisher.py  # pika wrapper with publisher confirms
│   ├── health.py              # /health endpoint
│   └── config.py              # env-var driven configuration
├── sql/
│   └── 001_create_idempotency_table.sql
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Notes for your Consumer Worker (next service)

- Consume from queue `maintenance_call_requested_queue`.
- Use the `idempotency_key` / `correlation_id` fields for your own
  logging + to correlate the ElevenLabs callback back to this event.
- `ack` only after the voice-bot call has been successfully triggered (or
  after you've durably recorded the job state) so a consumer crash
  doesn't silently drop a call request — RabbitMQ will redeliver
  un-acked messages.
