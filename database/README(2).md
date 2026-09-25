# dev-voice-db — SQL setup

Source: `Dev_voice_db2.sql` (PostgreSQL custom-format dump, PostgreSQL 16.13).

## Files

1. `01_create_database.sql` — creates database `dev-voice-db` if it does not exist and adds the database comment.
2. `02_create_schema.sql` — creates extensions, tables, identity columns, constraints, indexes, functions, and views.
3. `03_master_data.sql` — seeds the requested language and vehicle master data.

## Execution order

Connect to a PostgreSQL maintenance database (usually `postgres`) and run:

```text
01_create_database.sql
```

Then connect to `dev-voice-db` and run:

```text
02_create_schema.sql
03_master_data.sql
```

Example with `psql`:

```bash
psql -U postgres -f 01_create_database.sql
psql -U postgres -d dev-voice-db -f 02_create_schema.sql
psql -U postgres -d dev-voice-db -f 03_master_data.sql
```

## Notes

- The source dump uses the PostgreSQL custom/archive format even though its filename ends in `.sql`.
- The schema contains `driver`, `vehicle_assignment`, `vehicle_service`, `voice_bot_call_job`, and `voice_bot_call_job_event` in addition to the two master tables.
- `btree_gist` is required by the vehicle-assignment exclusion constraint.
- `pgcrypto` is required for `gen_random_uuid()` defaults.
- The vehicle master is seeded with the source vehicle registrations and external IDs, but `driver_id` is deliberately `NULL` because driver records were not requested as master data. Driver/vehicle assignments can be populated later.
- Database creation intentionally avoids hard-coding the source dump's Windows-specific `English_India.1252` locale, making the script more portable across PostgreSQL installations.
