"""
Database access layer.

Responsibilities:
1. Fetch services that are due for maintenance (per QUERY_MODE / LEAD_DAYS).
2. Provide an atomic "claim for publish" operation backed by a unique-keyed
   tracking table (dbo.MaintenanceCallIdempotency) so the same
   (service_id, due_maintenance_date, maintenance_type) combination never
   triggers two voice-bot calls, even if the scheduler picks the row up on
   more than one run.
"""
import logging
import pyodbc

from app.config import config

logger = logging.getLogger("publisher.db")


def get_connection() -> pyodbc.Connection:
    conn = pyodbc.connect(config.db_connection_string, autocommit=False)
    return conn


# ----------------------------------------------------------------------------
# Fetching due services
# ----------------------------------------------------------------------------

_BASE_SELECT = """
SELECT
    sr.service_id,
    v.carno,
    v.driver_name,
    v.driver_phone,
    sr.due_maintenance_date,
    sr.maintenance_type
FROM ServiceRecords sr
INNER JOIN Vehicles v
    ON v.vehicle_id = sr.vehicle_id
WHERE sr.service_status = 'DUE'
"""


def _build_query(mode: str):
    """Returns (sql, params) for the configured QUERY_MODE."""
    if mode == "asis":
        # Literal query as originally specified by the business:
        # everything due today or later, no upper bound.
        sql = _BASE_SELECT + " AND sr.due_maintenance_date >= CAST(SYSUTCDATETIME() AS DATE);"
        return sql, ()

    if mode == "exact":
        # Only rows whose due date is EXACTLY today + LEAD_DAYS.
        sql = (
            _BASE_SELECT
            + " AND sr.due_maintenance_date = "
              "CAST(DATEADD(DAY, ?, SYSUTCDATETIME()) AS DATE);"
        )
        return sql, (config.LEAD_DAYS,)

    # default: "window" -> due today through today + LEAD_DAYS (inclusive)
    sql = (
        _BASE_SELECT
        + " AND sr.due_maintenance_date BETWEEN "
          "CAST(SYSUTCDATETIME() AS DATE) AND "
          "CAST(DATEADD(DAY, ?, SYSUTCDATETIME()) AS DATE);"
    )
    return sql, (config.LEAD_DAYS,)


def fetch_due_services(conn: pyodbc.Connection):
    sql, params = _build_query(config.QUERY_MODE)
    cursor = conn.cursor()
    cursor.execute(sql, params) if params else cursor.execute(sql)

    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    return rows


# ----------------------------------------------------------------------------
# Idempotency
# ----------------------------------------------------------------------------

def build_idempotency_key(row: dict) -> str:
    due_date = row["due_maintenance_date"]
    due_date_str = due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date)
    return f"{row['service_id']}:{due_date_str}:{row['maintenance_type']}"


def claim_for_publish(conn: pyodbc.Connection, idempotency_key: str,
                       correlation_id: str, row: dict) -> bool:
    """
    Atomically decide whether THIS process should publish the event.

    Returns True  -> caller should publish (new row, or a previous PENDING/FAILED retry)
    Returns False -> already PUBLISHED previously, caller must skip (duplicate)

    Uses UPDLOCK/HOLDLOCK so two concurrent runs (e.g. an overlapping manual
    trigger) can't both decide to publish the same key.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT status FROM dbo.MaintenanceCallIdempotency WITH (UPDLOCK, HOLDLOCK)
            WHERE idempotency_key = ?
            """,
            idempotency_key,
        )
        existing = cursor.fetchone()

        if existing is None:
            cursor.execute(
                """
                INSERT INTO dbo.MaintenanceCallIdempotency
                    (idempotency_key, correlation_id, service_id, carno,
                     maintenance_type, due_maintenance_date, status, attempt_count)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 1)
                """,
                idempotency_key,
                correlation_id,
                row["service_id"],
                row["carno"],
                row["maintenance_type"],
                row["due_maintenance_date"],
            )
            conn.commit()
            return True

        status = existing[0]
        if status == "PUBLISHED":
            conn.commit()  # release the lock, nothing else to do
            logger.info("Skipping duplicate, already PUBLISHED: %s", idempotency_key)
            return False

        # PENDING or FAILED -> allow a retry, refresh the correlation id
        cursor.execute(
            """
            UPDATE dbo.MaintenanceCallIdempotency
            SET attempt_count = attempt_count + 1,
                correlation_id = ?,
                updated_at = SYSUTCDATETIME()
            WHERE idempotency_key = ?
            """,
            correlation_id,
            idempotency_key,
        )
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def mark_published(conn: pyodbc.Connection, idempotency_key: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE dbo.MaintenanceCallIdempotency
        SET status = 'PUBLISHED', updated_at = SYSUTCDATETIME(), last_error = NULL
        WHERE idempotency_key = ?
        """,
        idempotency_key,
    )
    conn.commit()
    cursor.close()


def mark_failed(conn: pyodbc.Connection, idempotency_key: str, error_message: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE dbo.MaintenanceCallIdempotency
        SET status = 'FAILED', updated_at = SYSUTCDATETIME(), last_error = ?
        WHERE idempotency_key = ?
        """,
        error_message[:1000],
        idempotency_key,
    )
    conn.commit()
    cursor.close()
