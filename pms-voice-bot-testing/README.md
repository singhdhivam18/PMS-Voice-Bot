# PMS Voice Bot Testing

`init_test_data.py` creates a deterministic test setup for the PMS voice-bot flow:

- Test driver with an English preferred language
- Test vehicle
- Current driver/vehicle assignment
- `DUE` vehicle-service record
- Service due **tomorrow**, so it falls within the next 2 days
- Verification against `v_pms_call_queue`

## Run

Install the PostgreSQL Python driver:

```bash
pip install "psycopg[binary]"
```

Then run:

```bash
python pms-voice-bot-testing/init_test_data.py
```

Defaults are aligned with the local PostgreSQL Docker service:

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=dev-voice-db
DB_USER=postgres
DB_PASSWORD=postgres
```

Override any value with environment variables when needed.
