
"""
Database access layer.

Responsibilities:
1. Fetch services due for maintenance.
2. Create or reuse exactly one voice_bot_call_job per service.
3. Prevent duplicate jobs for the same service_id.
4. Allow a FAILED job to be retried by reusing the same row.
5. Mark service/job state after publish success or failure.

PostgreSQL version.
"""

import logging

import pyodbc

from app.config import config


logger = logging.getLogger("publisher.db")


# Connection

def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(
        config.db_connection_string,
        autocommit=False,
    )


# Fetch due services

_BASE_SELECT = """
SELECT
    vs.id AS service_id,
    v.registration_no,
    d.name AS driver_name,
    d.phone AS driver_phone,
    l.code AS preferred_language,
    vs.due_maintenance_date,
    vs.maintenance_type
FROM public.vehicle_service vs
INNER JOIN public.vehicle v
    ON v.id = vs.vehicle_id
INNER JOIN public.driver d
    ON d.id = v.driver_id
INNER JOIN public.language l
    ON l.id = d.preferred_language_id
WHERE vs.service_status = 'DUE'
  AND v.is_active = TRUE
  AND d.do_not_call = FALSE
"""


def _build_query(mode: str):
    """
    QUERY_MODE:
        asis   -> due today or later
        exact  -> due exactly today + LEAD_DAYS
        window -> due today through today + LEAD_DAYS
    """

    if mode == "asis":
        sql = _BASE_SELECT + """
AND vs.due_maintenance_date >= CURRENT_DATE
"""
        return sql, ()

    if mode == "exact":
        sql = _BASE_SELECT + """
AND vs.due_maintenance_date =
    CURRENT_DATE + CAST(? AS INTEGER)
"""
        return sql, (config.LEAD_DAYS,)

    sql = _BASE_SELECT + """
AND vs.due_maintenance_date BETWEEN
    CURRENT_DATE
    AND CURRENT_DATE + CAST(? AS INTEGER)
"""

    return sql, (config.LEAD_DAYS,)


def fetch_due_services(conn: pyodbc.Connection):
    """Fetch services that are currently DUE according to QUERY_MODE."""

    sql, params = _build_query(config.QUERY_MODE)

    cursor = conn.cursor()

    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        columns = [column[0] for column in cursor.description]

        rows = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        logger.info(
            "Fetched %d due service(s)",
            len(rows),
        )

        return rows

    finally:
        cursor.close()


# Service ID

def get_service_id(row: dict) -> int:
    return int(row["service_id"])


# Claim for publish

def claim_for_publish(
    conn: pyodbc.Connection,
    service_id: int,
    correlation_id: str,
    row: dict,
) -> bool:
    """
    Ensure only one voice_bot_call_job exists for a service.

    If service_id already exists:
        -> do nothing
        -> return False

    If service_id does not exist:
        -> insert one PENDING job
        -> return True

    The UNIQUE constraint/index on service_id protects against
    concurrent inserts.
    """

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id,job_status
            FROM public.voice_bot_call_job
            WHERE service_id = ?
            LIMIT 1
            """,
            service_id,
        )

        existing = cursor.fetchone()
        if existing is not None:
            job_id = existing[0]
            job_status=existing[1]
            if job_status == "FAILED":
                cursor.execute(
                    """
                    UPDATE public.voice_bot_call_job
                    SET
                        correlation_id = ?,
                        job_status = 'PENDING',
                        callback_received = FALSE,
                        callback_payload_file_path = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    correlation_id,
                    job_id,
                )

                conn.commit()

            logger.info(
                "Skipping service_id=%s because job_id=%s already exists",
                service_id,
                job_id,
            )

            return False

        cursor.execute(
            """
            INSERT INTO public.voice_bot_call_job
            (
                service_id,
                correlation_id,
                job_status,
                callback_received,
                callback_payload_file_path
            )
            VALUES
            (
                ?,
                ?,
                'PENDING',
                FALSE,
                NULL
            )
            RETURNING id
            """,
            service_id,
            correlation_id,
        )

        inserted = cursor.fetchone()

        conn.commit()

        logger.info(
            "Created voice_bot_call_job: "
            "service_id=%s job_id=%s correlation_id=%s",
            service_id,
            inserted[0],
            correlation_id,
        )

        return True,job_id

    except Exception:
        conn.rollback()

        logger.exception(
            "Failed to create/check job for service_id=%s",
            service_id,
        )

        raise

    finally:
        cursor.close()


# Mark published

def mark_published(
    conn,
    *,
    job_id: int,
) -> None:

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE public.voice_bot_call_job
            SET
                job_status = 'Proccessing',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            job_id,
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"voice_bot_call_job not found: job_id={job_id}"
            )

        cursor.execute(
            """
            INSERT INTO public.voice_bot_call_job_event
            (
                job_id,
                event_status,
                system_message
            )
            VALUES
            (
                ?,
                'PUBLISHED',
                'Maintenance call event published to RabbitMQ successfully.'
            )
            """,
            job_id,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
# Mark failed

def mark_publish_failed(
    conn,
    *,
    job_id: int,
    error_message: str,
) -> None:
    """
    RabbitMQ publish failed.

    Keep the existing voice_bot_call_job row so the same job_id
    can be reused on the next retry.

    Update:
        job_status -> FAILED
        PUBLISHED event -> NOT_PUBLISHED
    """

    cursor = conn.cursor()

    try:
        # Update the latest PUBLISHED event for this job.
        cursor.execute(
            """
            UPDATE public.voice_bot_call_job_event
            SET
                event_status = 'NOT_PUBLISHED',
                system_message = ?,
                event_occurred_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id
                FROM public.voice_bot_call_job_event
                WHERE job_id = ?
                  AND event_status = 'PUBLISHED'
                ORDER BY id DESC
                LIMIT 1
            )
            """,
            error_message[:500],
            job_id,
        )

        if cursor.rowcount != 1:
            logger.warning(
                "No PUBLISHED event found for job_id=%s",
                job_id,
            )

        # Keep the job row and make it retryable.
        cursor.execute(
            """
            UPDATE public.voice_bot_call_job
            SET
                job_status = 'FAILED',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            job_id,
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"voice_bot_call_job not found: job_id={job_id}"
            )

        # Service remains due.
        cursor.execute(
            """
            UPDATE public.vehicle_service
            SET
                service_status = 'DUE'
            WHERE id = (
                SELECT service_id
                FROM public.voice_bot_call_job
                WHERE id = ?
            )
            """,
            job_id,
        )

        conn.commit()

        logger.error(
            "RabbitMQ publish failed: job_id=%s "
            "event=NOT_PUBLISHED error=%s",
            job_id,
            error_message,
        )

    except Exception:
        conn.rollback()

        logger.exception(
            "Failed to mark publish failure for job_id=%s",
            job_id,
        )

        raise

    finally:
        cursor.close()

def insert_job_event(
    conn,
    *,
    job_id: int,
    event_status: str,
    system_message: str,
) -> int:

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO public.voice_bot_call_job_event
            (
                job_id,
                event_status,
                system_message
            )
            VALUES
            (
                ?,
                ?,
                ?
            )
            RETURNING id
            """,
            job_id,
            event_status,
            system_message[:500],
        )

        row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                f"Failed to insert event for job_id={job_id}"
            )

        event_id = int(row[0])

        conn.commit()

        logger.info(
            "Inserted job event event_id=%s job_id=%s status=%s",
            event_id,
            job_id,
            event_status,
        )

        return event_id

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()