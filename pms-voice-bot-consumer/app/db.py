import json
import logging
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import config

logger = logging.getLogger("consumer.db")


def get_connection():
    """Open a PostgreSQL connection with explicit transaction control."""
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        connect_timeout=config.DB_CONNECT_TIMEOUT,
    )


def get_job_by_service_id(conn, service_id: int):
    """Return the newest existing voice job for the supplied service."""
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                id,
                external_id,
                service_id,
                correlation_id,
                job_status,
                callback_received,
                callback_payload_file_path
            FROM public.voice_bot_call_job
            WHERE service_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (service_id,),
        )
        return cursor.fetchone()


def get_job_by_correlation_id(conn, correlation_id: str):
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                id,
                external_id,
                service_id,
                correlation_id,
                job_status,
                callback_received,
                callback_payload_file_path
            FROM public.voice_bot_call_job
            WHERE correlation_id = %s::uuid
            LIMIT 1
            """,
            (correlation_id,),
        )
        return cursor.fetchone()


def insert_call_initiated_event(
    conn,
    *,
    job_id: int,
    system_message: str,
) -> int:
    with conn.cursor() as cursor:
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
                %s,
                'CALL_INITIATED',
                %s
            )
            RETURNING id
            """,
            (job_id, system_message[:500]),
        )
        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            f"Failed to insert CALL_INITIATED event for job_id={job_id}"
        )

    conn.commit()
    event_id = int(row[0])

    logger.info(
        "Inserted CALL_INITIATED event event_id=%s job_id=%s",
        event_id,
        job_id,
    )
    return event_id


def complete_call_from_callback(
    conn,
    *,
    job_id: int,
    callback_payload: dict[str, Any],
    callback_payload_file_path: str,
) -> None:
    """Complete the latest initiated event and update the existing job."""
    response_data = callback_payload.get("responseData")
    callback_message = "Voice call callback received successfully."

    if isinstance(response_data, dict):
        callback_message = json.dumps(
            response_data,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE public.voice_bot_call_job_event
            SET
                event_status = 'COMPLETED',
                system_message = %s,
                event_occurred_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id
                FROM public.voice_bot_call_job_event
                WHERE job_id = %s
                  AND event_status = 'CALL_INITIATED'
                ORDER BY id DESC
                LIMIT 1
            )
            RETURNING id
            """,
            (callback_message[:500], job_id),
        )
        event_row = cursor.fetchone()

        if event_row is None:
            raise RuntimeError(
                f"No CALL_INITIATED event found for job_id={job_id}"
            )

        cursor.execute(
            """
            UPDATE public.voice_bot_call_job
            SET
                job_status='COMPLETED',
                callback_received = TRUE,
                callback_payload_file_path = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (callback_payload_file_path, job_id),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Unable to update voice_bot_call_job job_id={job_id}"
            )

    conn.commit()

    logger.info(
        "Completed voice call event and updated job job_id=%s event_id=%s",
        job_id,
        event_row[0],
    )
