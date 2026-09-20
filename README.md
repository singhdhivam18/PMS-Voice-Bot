# PMS Voice Bot

## 1. Overview

PMS Voice Bot automates the periodic vehicle maintenance appointment workflow.

The pilot takes a maintenance-due vehicle record from SQL Server, publishes a maintenance event through RabbitMQ, consumes that event, initiates an automated voice call, processes the completed conversation, extracts the appointment result, and sends the result back to the Consumer for database processing.

### End-to-end architecture

```text
                         ┌─────────────────────┐
                         │     SQL Server      │
                         │    car-voice-db     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌────────────────────────────┐
                    │ PMS Voice Bot Publisher    │
                    │ Detect due maintenance     │
                    │ Idempotency + correlation   │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │   RabbitMQ     │
                         │ maintenance_   │
                         │ call_requested │
                         └───────┬────────┘
                                 │
                                 ▼
                    ┌────────────────────────────┐
                    │ PMS Voice Bot Consumer     │
                    │ Consume event              │
                    │ Create/update VoiceCallJob │
                    │ Trigger outbound call      │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                    ┌────────────────────────────┐
                    │ PMS Voice Bot              │
                    │ Orchestrator API :8000    │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │   ElevenLabs   │
                         │ AI conversation │
                         └───────┬────────┘
                                 │
                                 ▼
                              Twilio
                                 │
                                 ▼
                              Driver
                                 │
                                 │ conversation
                                 ▼
                    ┌────────────────────────────┐
                    │ ElevenLabs post-call       │
                    │ webhook                    │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                    ┌────────────────────────────┐
                    │ Orchestrator API            │
                    │ HMAC validation             │
                    │ Transcript persistence     │
                    │ Gemini extraction          │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                    ┌────────────────────────────┐
                    │ Consumer Callback API :9000│
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │   SQL Server   │
                         │ VoiceCallJobs  │
                         └────────────────┘
```

---

## 2. Services

### PMS Voice Bot Publisher

Responsible for:

- Reading maintenance records from SQL Server.
- Selecting eligible records based on `QUERY_MODE` and `LEAD_DAYS`.
- Creating an idempotency key for each maintenance event.
- Creating a correlation ID for end-to-end traceability.
- Publishing `maintenance_call_requested` events to RabbitMQ.
- Marking the event as published only after broker confirmation.
- Recording failed publish attempts so they can be retried later.

### PMS Voice Bot Consumer

Responsible for:

- Consuming maintenance events from RabbitMQ.
- Creating/resuming `VoiceCallJob`.
- Calling the PMS Voice Bot Orchestrator API.
- Persisting the `INITIATED` state after successful call initiation.
- Acknowledging the RabbitMQ delivery after the required durable state is committed.
- Receiving callback results from the Orchestrator.
- Updating the final call/job state in SQL Server.

The Consumer project also contains the Consumer Callback API on port `9000`.

### PMS Voice Bot Orchestrator API

Responsible for:

- Receiving outbound-call requests from the Consumer.
- Calling ElevenLabs for the AI voice conversation.
- Using the configured Twilio-integrated phone number for telephony.
- Receiving ElevenLabs post-call webhooks.
- Validating the webhook signature.
- Persisting call/transcript information.
- Sending the transcript to Gemini for structured appointment extraction.
- Returning the final business result to the Consumer Callback API.

---

# 3. Prerequisites

The local pilot requires:

- Python 3.12+
- SQL Server
- SQL Server database named `car-voice-db`
- RabbitMQ
- ElevenLabs account/configuration
- Twilio-integrated phone number through ElevenLabs
- Gemini API access
- ngrok for local post-call webhook testing

The external services and credentials are environment-specific and must be configured before running the system.

---

# 4. Repository structure

Recommended repository layout:

```text
pms-voice-bot/
│
├── README.md
├── .gitignore
│
├── database/
│   ├── README.md
│   └── 01_create_service_records.sql
│
├── pms-voice-bot-publisher/
│   ├── app/
│   ├── .env.example
│   ├── requirements.txt
│   └── ...
│
├── pms-voice-bot-consumer/
│   ├── app/
│   ├── .env.example
│   ├── requirements.txt
│   └── ...
│
└── pms-voice-bot-orchestrator/
    ├── app/
    ├── .env.example
    ├── requirements.txt
    └── ...
```

---

# 5. Database setup

## 5.1 Database

The pilot uses:

```text
Database: car-voice-db
```

The `ServiceRecords` table contains the maintenance records consumed by the Publisher.

The supplied database script creates:

```text
dbo.ServiceRecords
```

and references:

```text
dbo.Vehicles(vehicle_id)
```

Therefore `dbo.Vehicles` must exist before the `ServiceRecords` script is executed.

Run the database scripts in SQL Server Management Studio or another SQL Server client.

Current database script:

```text
database/01_create_service_records.sql
```

## 5.2 Required application data

The Publisher expects maintenance records with at least:

```text
service_id
vehicle_id
due_maintenance_date
maintenance_type
service_status
created_at
```

The related vehicle record must contain:

```text
vehicle_id
carno
driver_name
driver_phone
created_at
```

## 5.3 Insert a test vehicle and maintenance record

Use a test-only driver/phone number appropriate for your environment.

Example:

```sql
INSERT INTO [car-voice-db].[dbo].[Vehicles]
    ([carno], [driver_name], [driver_phone], [created_at])
VALUES
    ('KA01AB9995', '<TEST_DRIVER_NAME>', '<TEST_DRIVER_PHONE>', GETDATE());

DECLARE @vehicle_id INT;

SELECT @vehicle_id = [vehicle_id]
FROM [car-voice-db].[dbo].[Vehicles]
WHERE [carno] = 'KA01AB9995';

INSERT INTO [car-voice-db].[dbo].[ServiceRecords]
    ([vehicle_id],
     [due_maintenance_date],
     [maintenance_type],
     [service_status],
     [created_at])
VALUES
    (@vehicle_id,
     '2026-09-15',
     'REGULAR',
     'DUE',
     GETDATE());
```

The `service_status` must be `DUE` for the Publisher to consider the record.

Do not commit real driver phone numbers or personal data to GitHub.

---

# 6. RabbitMQ setup

The Publisher uses a topic exchange and a durable queue.

Current configuration:

```text
Exchange:
car_service_events

Exchange type:
topic

Routing key:
maintenance.call.requested

Queue:
maintenance_call_requested_queue
```

Logical flow:

```text
Publisher
    ↓
car_service_events
    ↓
maintenance.call.requested
    ↓
maintenance_call_requested_queue
    ↓
Consumer
```

RabbitMQ must be running before starting the Publisher and Consumer.

The exact username/password depends on the local RabbitMQ environment and should be configured through each service's `.env` file.

---

# 7. Environment configuration

Each service has its own `.env.example`.

Create a local `.env` from the example:

```powershell
Copy-Item .env.example .env
```

Do this separately inside each service directory.

Never commit the real `.env` files.

## 7.1 Publisher environment

File:

```text
pms-voice-bot-publisher/.env.example
```

Important settings include:

```env
DB_SERVER=localhost
DB_PORT=1433
DB_NAME=car-voice-db
DB_USER=sa
DB_PASSWORD=<set-locally>

RABBITMQ_URL=amqp://<rabbitmq-user>:<rabbitmq-password>@localhost:5672/%2F
RABBITMQ_EXCHANGE=car_service_events
RABBITMQ_EXCHANGE_TYPE=topic
RABBITMQ_ROUTING_KEY=maintenance.call.requested
RABBITMQ_QUEUE=maintenance_call_requested_queue
RABBITMQ_PUBLISH_CONFIRM=true

QUERY_MODE=window
LEAD_DAYS=2

RUN_MODE=loop
SCHEDULE_INTERVAL_MINUTES=60
RUN_IMMEDIATELY_ON_START=true

HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_PORT=8080

LOG_LEVEL=INFO
```

### Query modes

`window`:

```text
today <= due_date <= today + LEAD_DAYS
```

`exact`:

```text
due_date == today + LEAD_DAYS
```

`asis`:

```text
due_date >= today
```

With:

```text
QUERY_MODE=window
LEAD_DAYS=2
```

a record due on the 19th can be selected on the 17th, 18th, and 19th. The Publisher's idempotency mechanism prevents the same maintenance event from being published repeatedly.

## 7.2 Consumer environment

File:

```text
pms-voice-bot-consumer/.env.example
```

The current Consumer configuration includes:

```env
DB_SERVER=localhost
DB_PORT=1433
DB_NAME=car-voice-db
DB_USER=sa
DB_PASSWORD=<set-locally>
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_ENCRYPT=yes
DB_TRUST_SERVER_CERTIFICATE=yes
DB_CONN_TIMEOUT=10

RABBITMQ_URL=amqp://<rabbitmq-user>:<rabbitmq-password>@localhost:5672/%2F
RABBITMQ_EXCHANGE=car_service_events
RABBITMQ_EXCHANGE_TYPE=topic
RABBITMQ_QUEUE=maintenance_call_requested_queue
RABBITMQ_ROUTING_KEY=maintenance.call.requested

HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_PORT=8081

VOICE_AGENT_BASE_URL=http://127.0.0.1:8000

VOICE_AGENT_CALLBACK_URL=<configured-callback-url>

VOICE_AGENT_DEPOT_NAME=Bangalore Central Depot

VOICE_AGENT_TIMEOUT=<current-configured-value>

LOG_LEVEL=INFO
```

The Consumer's `VOICE_AGENT_BASE_URL` points to the local Orchestrator API.

The `VOICE_AGENT_CALLBACK_URL` is environment-specific. For local development it may use the configured callback path, while any public endpoint must be configured according to the deployment environment.

## 7.3 Orchestrator environment

File:

```text
pms-voice-bot-orchestrator/.env.example
```

Example structure:

```env
# ElevenLabs / Twilio

ELEVENLABS_API_KEY=

ELEVENLABS_AGENT_ID=agent_7901m24tek7bf7xrn1wqvzbdawyz

ELEVENLABS_AGENT_PHONE_NUMBER_ID=phnum_8201m24vrz0kfbas7gxs1jf06mwt

ELEVENLABS_CALL_RECORDING_ENABLED=false

ELEVENLABS_WEBHOOK_SECRET=
ELEVENLABS_WEBHOOK_MAX_AGE_SECONDS=300

# Local test data

TEST_DRIVER_NAME=<test-driver-name>
TEST_DRIVER_PHONE=<test-driver-phone>
TEST_CAR_NUMBER=<test-car-number>
TEST_DUE_DATE=<test-due-date>
TEST_DEPOT_NAME=Bangalore Central Depot
TEST_CORRELATION_ID=svc-demo-001
```

The real API key and webhook secret must be configured locally and must not be committed.

The `TEST_*` values are intended for local/manual testing.

---

# 8. Install Python dependencies

Create a virtual environment separately for each service.

## Publisher

```powershell
cd pms-voice-bot-publisher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Consumer

```powershell
cd pms-voice-bot-consumer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Orchestrator

```powershell
cd pms-voice-bot-orchestrator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

# 9. Start the system

Start SQL Server and RabbitMQ first.

Then run the application services in separate terminals.

Recommended order:

```text
1. Consumer Callback API
2. Orchestrator API
3. Consumer Worker
4. Publisher Worker
```

The Publisher can run after the downstream services are available.

---

# 10. Start the Consumer Callback API

From:

```text
pms-voice-bot-consumer
```

run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.callback_api:app --host 0.0.0.0 --port 9000
```

Expected endpoint:

```text
http://127.0.0.1:9000
```

This API receives the business result from the Orchestrator and updates the Consumer-side job/database state.

---

# 11. Start the Orchestrator API

From:

```text
pms-voice-bot-orchestrator
```

run:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
```

Alternative production-style local startup:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Use the command that matches the actual project entry point.

The Orchestrator exposes the outbound-call API and the ElevenLabs post-call webhook.

---

# 12. Expose the Orchestrator webhook for local development

ElevenLabs needs a publicly reachable HTTPS endpoint to send the post-call webhook during local development.

Start ngrok:

```powershell
ngrok http 8000
```

Ngrok will provide a public HTTPS URL.

The ElevenLabs post-call webhook should point to:

```text
https://<ngrok-host>/api/webhooks/elevenlabs/post-call
```

Example structure:

```text
https://<public-host>/api/webhooks/elevenlabs/post-call
        ↓
local machine
        ↓
Orchestrator :8000
```

Ngrok is development infrastructure only. In a deployed environment, use a public HTTPS endpoint provided by the deployment environment.

---

# 13. Start the Consumer Worker

From:

```text
pms-voice-bot-consumer
```

run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
```

The Consumer should connect to RabbitMQ and wait for:

```text
maintenance.call.requested
```

events.

---

# 14. Start the Publisher Worker

From:

```text
pms-voice-bot-publisher
```

run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
```

For a one-time publish run:

```powershell
$env:RUN_MODE="once"
python -m app.main
```

For loop mode:

```powershell
$env:RUN_MODE="loop"
python -m app.main
```

The environment value can also be stored in the Publisher `.env`.

---

# 15. End-to-end execution

A successful transaction follows this sequence.

### Step 1 - Maintenance record

SQL Server contains:

```text
service_status = DUE
```

with:

```text
service_id
vehicle_id
due_maintenance_date
maintenance_type
```

### Step 2 - Publisher selection

The Publisher applies:

```text
QUERY_MODE
LEAD_DAYS
```

and identifies an eligible service.

### Step 3 - Idempotency

The Publisher creates:

```text
service_id:due_maintenance_date:maintenance_type
```

Example:

```text
5001:2026-09-19:REGULAR
```

This protects the same maintenance event from being published repeatedly.

### Step 4 - Correlation

A correlation ID is created so the transaction can be traced across the system.

### Step 5 - RabbitMQ

The Publisher publishes:

```text
maintenance_call_requested
```

to the configured RabbitMQ exchange/routing key.

### Step 6 - Consumer

The Consumer consumes the event and creates/resumes the corresponding `VoiceCallJob`.

### Step 7 - Outbound call

The Consumer calls:

```text
POST /api/outbound-call
```

on the Orchestrator.

### Step 8 - ElevenLabs / Twilio

The Orchestrator requests the outbound call through ElevenLabs.

The configured Twilio-integrated phone number provides the telephony connection.

### Step 9 - INITIATED state

After the outbound-call request has been accepted:

```text
VoiceCallJob
    ↓
call_status = INITIATED
```

The Consumer then acknowledges the RabbitMQ message according to its processing semantics.

`INITIATED` does not mean the appointment conversation is complete.

### Step 10 - Driver conversation

The ElevenLabs agent conducts the maintenance conversation.

### Step 11 - Post-call webhook

After the conversation, ElevenLabs sends the signed post-call webhook to:

```text
/api/webhooks/elevenlabs/post-call
```

### Step 12 - Webhook validation

The Orchestrator validates the webhook signature before processing the payload.

### Step 13 - Transcript processing

The conversation transcript is persisted and sent to Gemini for structured appointment extraction.

### Step 14 - Consumer callback

The Orchestrator sends the resulting business data to:

```text
/api/voice/callback
```

on the Consumer Callback API.

### Step 15 - Database update

The Consumer updates the `VoiceCallJob` and related database state.

---

# 16. Voice conversation scenarios

The pilot conversation contains two primary paths.

## Case 1 - Driver does not want to book

Initial message:

```text
Hi {{Driver_Name}}

This is an automated reminder that your car
{{Car_Registration_Number}} is due for periodic
maintenance service on {{Due_date}}.

Would you like to book an appointment?
```

If the driver says no:

```text
Are you sure you don't want to book an appointment?
```

If the driver confirms that they do not want an appointment:

```text
Thank You
```

The resulting business state should represent that the appointment was not confirmed.

## Case 2 - Driver accepts

Initial message:

```text
Hi {{Driver_Name}}

This is an automated reminder that your car
{{Car_Registration_Number}} is due for periodic
maintenance service on {{Due_date}}.

Would you like to book an appointment?
```

If the driver says yes:

```text
Please confirm the date
```

After the driver provides the date:

```text
Please confirm the time
```

After the driver provides the time:

```text
Just to confirm you would be dropping your vehicle
on {{Input_date}} at {{Input_Time}}
```

If the driver confirms:

```text
Thank you for your confirmation,
we will create an appointment and share the details with you shortly.
```

Gemini then extracts structured appointment information from the completed conversation.

---

# 17. Reliability and recovery

## Idempotency

The Publisher may run repeatedly. A service due on a future date can remain inside the configured maintenance window across multiple runs.

The idempotency key:

```text
service_id:due_maintenance_date:maintenance_type
```

prevents repeated publication of the same maintenance event.

Different vehicles with the same due date have different `service_id` values, so they remain separate maintenance events.

Example:

```text
5001:2026-09-19:REGULAR
5002:2026-09-19:REGULAR
```

These are two different events.

## Correlation

The correlation ID provides end-to-end traceability through:

```text
Publisher
→ RabbitMQ
→ Consumer
→ Orchestrator
→ ElevenLabs
→ callback
→ database
```

## Asynchronous call completion

The call request is asynchronous.

The following are different states:

```text
INITIATED
```

means the outbound call request was accepted.

```text
COMPLETED
```

represents final post-call business processing.

The system should not interpret `INITIATED` as final appointment success.

## No-answer / busy / failed call

Retry logic should be based on explicit call outcomes such as:

```text
NO_ANSWER
BUSY
FAILED
```

rather than simply checking:

```text
callback_received = 0
```

A missing callback can also mean that a call completed successfully but the webhook result was not delivered.

## Webhook recovery

A missing webhook should not automatically trigger another outbound call.

The safer approach is to reconcile the provider-side call/conversation state before deciding that another call is required.

## Concurrent calls to the same phone number

Different maintenance records can legitimately have different idempotency keys while using the same driver phone number.

For example:

```text
Vehicle 352 → Driver phone X
Vehicle 456 → Driver phone X
```

These are different maintenance events, but the Consumer should control concurrent calls to the same destination so that two calls are not initiated simultaneously to the same phone.

The pilot should validate this behavior before higher-volume rollout.

## Outbound dispatch rate

RabbitMQ queue depth should not be treated as the provider capacity limit.

For higher volumes, the Consumer should control outbound call dispatch rate and active-call concurrency according to the configured provider limits.

---

# 18. Useful ports

| Component | Port |
|---|---:|
| PMS Voice Bot Orchestrator API | `8000` |
| PMS Voice Bot Consumer Callback API | `9000` |
| PMS Voice Bot Publisher Health Check | `8080` |
| PMS Voice Bot Consumer Health Check | `8081` |
| RabbitMQ AMQP | `5672` |

The actual health endpoints and additional management ports depend on the service configuration.

---

# 19. Expected logs

## Publisher

A successful run should contain messages similar to:

```text
Fetched N due service record(s)
Published event correlation_id=...
Run summary: {'fetched': N, 'published': 1, ...}
```

When an event has already been handled:

```text
Skipping duplicate, already PUBLISHED: <idempotency-key>
```

## Consumer

Look for:

```text
RabbitMQ message received
VoiceCallJob created/updated
Voice Agent call initiated successfully
VoiceCallJob marked CALL INITIATED
RabbitMQ message ACKed
```

The exact log wording depends on the current implementation.

## Orchestrator

Look for:

```text
outbound-call request
call_initiated
post-call webhook
signature verification
transcript processing
Gemini response
Consumer callback
```

---

# 20. Troubleshooting

## Uvicorn launcher points to an old virtual environment

If Windows reports something such as:

```text
E:\consumer-worker\.venv\Scripts\python.exe
```

while the project is now in a different directory, the copied virtual environment may contain an old executable path.

Recreate the virtual environment:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Use:

```powershell
python -m uvicorn ...
```

to avoid stale launcher executables.

## RabbitMQ `WinError 10053`

If a long-lived Pika connection is aborted:

```text
ConnectionAbortedError: [WinError 10053]
pika.exceptions.StreamLostError
```

check:

- RabbitMQ is running.
- The RabbitMQ URL is correct.
- The Publisher connection heartbeat is configured as intended by the current implementation.
- The application recreates a failed connection before the next publish.

## RabbitMQ queue is empty

An empty queue does not automatically mean publishing failed.

A running Consumer can consume the message almost immediately.

Check:

```text
Publisher logs
Consumer logs
RabbitMQ message rate / consumers
```

together.

## Duplicate maintenance record

Check the idempotency key:

```text
service_id:due_maintenance_date:maintenance_type
```

and the corresponding state in:

```text
dbo.MaintenanceCallIdempotency
```

## Two calls going to the same phone

Check whether two different maintenance records have the same `driver_phone`.

Different idempotency keys can still represent the same phone destination.

This is a Consumer-side call-concurrency concern rather than a Publisher idempotency failure.

---

# 21. Security and GitHub rules

Never commit:

```text
.env
.venv/
__pycache__/
*.log
calls/
```

Never commit:

- SQL Server passwords
- RabbitMQ passwords
- ElevenLabs API keys
- ElevenLabs webhook secrets
- Gemini API keys
- real driver phone numbers
- real production transcripts
- other sensitive call data

Commit `.env.example` files containing placeholders.

---

# 22. Pilot status

The English-language pilot validates the end-to-end path:

- maintenance record detection
- maintenance event publishing
- RabbitMQ consumption
- outbound call initiation
- ElevenLabs/Twilio voice interaction
- post-call webhook processing
- transcript persistence
- Gemini appointment extraction
- Consumer callback
- database state update

The stabilization phase should validate:

- no-answer handling
- busy handling
- failed call handling
- retry behavior
- webhook recovery/reconciliation
- duplicate-call prevention
- same-phone concurrent-call control
- outbound call rate/concurrency control
- repeated scheduler execution
- provider/API failure scenarios

---

# 23. Quick-start checklist

Before starting:

```text
[ ] SQL Server is running
[ ] car-voice-db exists
[ ] Vehicles table exists
[ ] ServiceRecords exists
[ ] Test DUE record exists
[ ] RabbitMQ is running
[ ] Publisher .env configured
[ ] Consumer .env configured
[ ] Orchestrator .env configured
[ ] ElevenLabs API key configured
[ ] ElevenLabs webhook secret configured
[ ] ElevenLabs agent/phone number configured
[ ] Gemini configuration configured
[ ] ngrok running for local post-call webhooks
```

Then start:

```text
1. Consumer Callback API :9000
2. Orchestrator API :8000
3. Consumer Worker
4. Publisher Worker
```

Finally verify:

```text
SQL DUE record
    ↓
Publisher log
    ↓
RabbitMQ event
    ↓
Consumer log
    ↓
Call initiated
    ↓
Driver conversation
    ↓
Post-call webhook
    ↓
Gemini result
    ↓
Consumer callback
    ↓
SQL Server job/result update
```

---

# 24. Service-specific documentation

Each service directory contains its own `README.md` for quick service-level usage:

```text
pms-voice-bot-publisher/README.md
pms-voice-bot-consumer/README.md
pms-voice-bot-orchestrator/README.md
```

The root `README.md` is the primary document for complete end-to-end setup and execution.
