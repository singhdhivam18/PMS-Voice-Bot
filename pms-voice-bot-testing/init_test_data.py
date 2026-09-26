"""Initialize deterministic test data for the PMS voice-bot flow.

This script creates/updates one driver, one vehicle, a current vehicle
assignment, and one DUE vehicle-service record whose maintenance date is
one day from the date on which the script is run.

It is intentionally idempotent: running it multiple times reuses the same
phone number/registration number and refreshes the test service record.

Requirements:
    pip install "psycopg[binary]"

Example:
    python pms-voice-bot-testing/init_test_data.py

Environment variables (defaults are suitable for the local docker-compose
PostgreSQL service):
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=dev-voice-db
    DB_USER=postgres
    DB_PASSWORD=postgres
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

try:
    import psycopg
except ImportError:  # pragma: no cover - gives a clearer CLI error
    print(
        'Missing dependency: psycopg. Install it with: '
        'pip install "psycopg[binary]"',
        file=sys.stderr,
    )
    raise SystemExit(1)


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "dev-voice-db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Test@123")

# Stable values make the script safe to execute repeatedly.
TEST_DRIVER_PHONE = os.getenv("TEST_DRIVER_PHONE", "+919980014906")
TEST_DRIVER_NAME = os.getenv("TEST_DRIVER_NAME", "Ayush")
TEST_VEHICLE_REGISTRATION = os.getenv(
    "TEST_VEHICLE_REGISTRATION",
    "KA01AB1532",
)
TEST_MAINTENANCE_TYPE = os.getenv(
    "TEST_MAINTENANCE_TYPE",
    "Regular",
)
TEST_LANGUAGE_CODE = os.getenv("TEST_LANGUAGE_CODE", "hi")


def get_connection() -> psycopg.Connection:
    """Open a PostgreSQL connection using the standard DB_* variables."""

    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def init_test_data() -> None:
    """Create a complete PMS call-queue test record."""

    due_date = date.today() + timedelta(days=1)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # The schema's master-data script should already contain English.
            # We fail clearly rather than silently choosing the wrong language.
            cur.execute(
                """
                SELECT id
                FROM public.language
                WHERE code = %s
                LIMIT 1
                """,
                (TEST_LANGUAGE_CODE,),
            )
            language_row = cur.fetchone()
            if language_row is None:
                raise RuntimeError(
                    f"Language code {TEST_LANGUAGE_CODE!r} was not found. "
                    "Run the master-data SQL first."
                )

            language_id = language_row[0]

            # Create/reuse the test driver.
            cur.execute(
                """
                INSERT INTO public.driver
                    (name, phone, preferred_language_id, language_source, do_not_call)
                VALUES
                    (%s, %s, %s, 'manual', FALSE)
                ON CONFLICT (phone) DO UPDATE
                SET name = EXCLUDED.name,
                    preferred_language_id = EXCLUDED.preferred_language_id,
                    language_source = EXCLUDED.language_source,
                    do_not_call = FALSE,
                    updated_at = CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
                RETURNING id
                """,
                (TEST_DRIVER_NAME, TEST_DRIVER_PHONE, language_id),
            )
            driver_id = cur.fetchone()[0]

            # Create/reuse the test vehicle. Keep driver_id NULL here; the
            # current assignment below is the source of truth for the queue.
            cur.execute(
                """
                INSERT INTO public.vehicle
                    (registration_no, driver_id, is_active)
                VALUES
                    (%s, NULL, TRUE)
                ON CONFLICT (registration_no) DO UPDATE
                SET is_active = TRUE
                RETURNING id
                """,
                (TEST_VEHICLE_REGISTRATION,),
            )
            vehicle_id = cur.fetchone()[0]

            # Ensure this test vehicle has exactly one current assignment.
            # The unique partial index on (vehicle_id WHERE assigned_to IS NULL)
            # makes this safe and prevents duplicate active assignments.
            cur.execute(
                """
                SELECT id, driver_id
                FROM public.vehicle_assignment
                WHERE vehicle_id = %s
                  AND assigned_to IS NULL
                LIMIT 1
                """,
                (vehicle_id,),
            )
            current_assignment = cur.fetchone()

            if current_assignment is None:
                cur.execute(
                    """
                    INSERT INTO public.vehicle_assignment
                        (vehicle_id, driver_id, assigned_from)
                    VALUES
                        (%s, %s, %s)
                    RETURNING id
                    """,
                    (vehicle_id, driver_id, now_utc),
                )
                assignment_id = cur.fetchone()[0]
            else:
                assignment_id, assigned_driver_id = current_assignment
                if assigned_driver_id != driver_id:
                    cur.execute(
                        """
                        UPDATE public.vehicle_assignment
                        SET assigned_to = %s
                        WHERE id = %s
                        """,
                        (now_utc, assignment_id),
                    )
                    cur.execute(
                        """
                        INSERT INTO public.vehicle_assignment
                            (vehicle_id, driver_id, assigned_from)
                        VALUES
                            (%s, %s, %s)
                        RETURNING id
                        """,
                        (vehicle_id, driver_id, now_utc),
                    )
                    assignment_id = cur.fetchone()[0]

            # Keep vehicle.driver_id aligned with the active assignment for
            # consumers that inspect the vehicle table directly.
            cur.execute(
                """
                UPDATE public.vehicle
                SET driver_id = %s,
                    is_active = TRUE
                WHERE id = %s
                """,
                (driver_id, vehicle_id),
            )

            # Refresh one deterministic DUE service record for this test vehicle.
            # The date is dynamically one day from execution, so it is always
            # inside the requested next-two-days test window.
            cur.execute(
                """
                UPDATE public.vehicle_service
                SET due_maintenance_date = %s,
                    service_status = 'DUE',
                    call_attempts = 0
                WHERE vehicle_id = %s
                  AND maintenance_type = %s
                RETURNING id
                """,
                (due_date, vehicle_id, TEST_MAINTENANCE_TYPE),
            )
            existing_service = cur.fetchone()

            if existing_service is None:
                cur.execute(
                    """
                    INSERT INTO public.vehicle_service
                        (
                            vehicle_id,
                            due_maintenance_date,
                            maintenance_type,
                            service_status,
                            call_attempts
                        )
                    VALUES
                        (%s, %s, %s, 'DUE', 0)
                    RETURNING id
                    """,
                    (vehicle_id, due_date, TEST_MAINTENANCE_TYPE),
                )
                service_id = cur.fetchone()[0]
            else:
                service_id = existing_service[0]

            conn.commit()

            print("PMS voice-bot test data initialized successfully.")
            print(f"  language_id       : {language_id}")
            print(f"  driver_id         : {driver_id}")
            print(f"  vehicle_id        : {vehicle_id}")
            print(f"  assignment_id     : {assignment_id}")
            print(f"  vehicle_service_id: {service_id}")
            print(f"  registration_no   : {TEST_VEHICLE_REGISTRATION}")
            print(f"  driver_phone      : {TEST_DRIVER_PHONE}")
            print(f"  due_date          : {due_date} (tomorrow)")
            print(f"  service_status    : DUE")

            # This mirrors the application's call-queue view and gives an
            # immediate verification that the record is visible to the PMS flow.
            cur.execute(
                """
                SELECT vehicle_service_id, driver_id, driver_phone, due_maintenance_date
                FROM public.v_pms_call_queue
                WHERE vehicle_service_id = %s
                """,
                (service_id,),
            )
            queue_row = cur.fetchone()
            if queue_row:
                print("  queue_visibility  : READY (v_pms_call_queue)")
            else:
                print(
                    "  queue_visibility  : NOT VISIBLE in v_pms_call_queue",
                    file=sys.stderr,
                )


def main() -> int:
    try:
        init_test_data()
    except Exception as exc:
        print(f"Failed to initialize PMS test data: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
