import json
import logging

import pyodbc

from app.config import config

logger = logging.getLogger("consumer.db")


def get_connection():
    return pyodbc.connect(
        config.db_connection_string,
        autocommit=False,
    )


def get_job_by_idempotency_key(
    conn,
    idempotency_key: str,
):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            job_id,
            service_id,
            idempotency_key,
            correlation_id,
            job_status,
            call_status,
            provider_call_id,
            attempt_count
        FROM dbo.VoiceCallJobs
        WHERE idempotency_key = ?
        """,
        idempotency_key,
    )

    return cursor.fetchone()


def create_job(
    conn,
    *,
    service_id: int,
    idempotency_key: str,
    correlation_id: str,
) -> int:
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO dbo.VoiceCallJobs
        (
            service_id,
            idempotency_key,
            correlation_id,
            job_status,
            call_status,
            attempt_count,
            consumed_at,
            updated_at
        )
        OUTPUT INSERTED.job_id
        VALUES
        (
            ?,
            ?,
            ?,
            'PROCESSING',
            'NOT_STARTED',
            1,
            SYSUTCDATETIME(),
            SYSUTCDATETIME()
        )
        """,
        service_id,
        idempotency_key,
        correlation_id,
    )

    row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Failed to create VoiceCallJob"
        )

    job_id = int(row[0])

    conn.commit()

    logger.info(
        "Created VoiceCallJob "
        "job_id=%s correlation_id=%s",
        job_id,
        correlation_id,
    )

    return job_id


def mark_poc_completed(
    conn,
    *,
    job_id: int,
    result: dict,
):
    cursor = conn.cursor()

    callback_payload = json.dumps(
        result,
        ensure_ascii=False,
    )

    cursor.execute(
        """
        UPDATE dbo.VoiceCallJobs
        SET
            job_status = 'COMPLETED',
            call_status = 'COMPLETED',
            callback_received = 1,
            callback_payload = ?,
            last_error = NULL,
            updated_at = SYSUTCDATETIME(),
            completed_at = SYSUTCDATETIME()
        WHERE job_id = ?
        """,
        callback_payload,
        job_id,
    )

    if cursor.rowcount != 1:
        raise RuntimeError(
            f"Unable to complete VoiceCallJob "
            f"job_id={job_id}"
        )

    conn.commit()

    logger.info(
        "VoiceCallJob marked COMPLETED "
        "job_id=%s",
        job_id,
    )


def mark_poc_failed(
    conn,
    *,
    job_id: int,
    error_message: str,
    result: dict | None = None,
):
    cursor = conn.cursor()

    callback_payload = (
        json.dumps(
            result,
            ensure_ascii=False,
        )
        if result is not None
        else None
    )

    cursor.execute(
        """
        UPDATE dbo.VoiceCallJobs
        SET
            job_status = 'FAILED',
            call_status = 'FAILED',
            callback_received = 1,
            callback_payload = ?,
            last_error = ?,
            updated_at = SYSUTCDATETIME()
        WHERE job_id = ?
        """,
        callback_payload,
        error_message,
        job_id,
    )

    if cursor.rowcount != 1:
        raise RuntimeError(
            f"Unable to mark VoiceCallJob "
            f"job_id={job_id} as FAILED"
        )

    conn.commit()

    logger.info(
        "VoiceCallJob marked FAILED "
        "job_id=%s",
        job_id,
    )
def mark_call_initiated(
    conn,
    *,
    job_id: int,
    result: dict,
):
    cursor = conn.cursor()

    callback_payload = json.dumps(
        result,
        ensure_ascii=False,
    )

    cursor.execute(
        """
        UPDATE dbo.VoiceCallJobs
        SET
            job_status = 'PROCESSING',
            call_status = 'INITIATED',
            callback_received = 0,
            callback_payload = ?,
            last_error = NULL,
            updated_at = SYSUTCDATETIME()
        WHERE job_id = ?
        """,
        callback_payload,
        job_id,
    )

    if cursor.rowcount != 1:
        raise RuntimeError(
            f"Unable to mark VoiceCallJob "
            f"job_id={job_id} as call initiated"
        )

    conn.commit()

    logger.info(
        "VoiceCallJob marked CALL INITIATED "
        "job_id=%s",
        job_id,
    )
def get_job_by_correlation_id(
    conn,
    *,
    correlation_id: str,
):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            job_id,
            service_id,
            idempotency_key,
            correlation_id,
            job_status,
            call_status,
            provider_call_id,
            attempt_count
        FROM dbo.VoiceCallJobs
        WHERE correlation_id = ?
        """,
        correlation_id,
    )

    return cursor.fetchone()
