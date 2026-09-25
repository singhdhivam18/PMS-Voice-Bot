
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
    vs.due_maintenance_date,
    vs.maintenance_type
FROM public.vehicle_service vs
INNER JOIN public.vehicle v
    ON v.id = vs.vehicle_id
INNER JOIN public.driver d
    ON d.id = v.driver_id
WHERE vs.service_status = 'DUE'
  AND v.is_active = TRUE
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
            SELECT id
            FROM public.voice_bot_call_job
            WHERE service_id = ?
            LIMIT 1
            """,
            service_id,
        )

        existing = cursor.fetchone()

        if existing is not None:
            job_id = existing[0]

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

        return True

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
    conn: pyodbc.Connection,
    service_id: int,
) -> None:
    """
    When the call job is COMPLETED:
        service_status = BOOKED
        call_attempts = call_attempts + 1
    """

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT job_status
            FROM public.voice_bot_call_job
            WHERE service_id = ?
            """,
            service_id,
        )

        existing = cursor.fetchone()

        if existing is None:
            logger.warning(
                "No voice_bot_call_job found for service_id=%s",
                service_id,
            )
            return

        status = existing[0]

        if status == "COMPLETED":
            cursor.execute(
                """
                UPDATE public.vehicle_service
                SET
                    service_status = 'BOOKED',
                    call_attempts = call_attempts + 1
                WHERE id = ?
                """,
                service_id,
            )

            conn.commit()

            logger.info(
                "Service completed and marked BOOKED: service_id=%s",
                service_id,
            )

        else:
            conn.commit()

            logger.info(
                "Service_id=%s job status=%s; no completion update",
                service_id,
                status,
            )

    except Exception:
        conn.rollback()

        logger.exception(
            "Failed to mark service_id=%s as BOOKED",
            service_id,
        )

        raise

    finally:
        cursor.close()


# Mark failed

def mark_publish_failed(
    conn: pyodbc.Connection,
    service_id: int,
    error_message: str,
) -> None:
    """
    The publisher failed to send the RabbitMQ message.

    Since the message was never successfully published, remove the
    pending job record so the next scheduler run can create a new one.

    This is not a voice-bot job failure.
    """

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM public.voice_bot_call_job
            WHERE service_id = ?
            """,
            service_id,
        )

        cursor.execute(
            """
            UPDATE public.vehicle_service
            SET service_status = 'DUE'
            WHERE id = ?
            """,
            service_id,
        )

        conn.commit()

        logger.error(
            "Publisher failed for service_id=%s. "
            "Job removed so it can be retried: %s",
            service_id,
            error_message,
        )

    except Exception:
        conn.rollback()

        logger.exception(
            "Failed to handle publisher failure for service_id=%s",
            service_id,
        )

        raise

    finally:
        cursor.close()
