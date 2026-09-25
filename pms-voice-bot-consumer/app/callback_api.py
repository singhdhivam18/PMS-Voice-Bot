import logging
from typing import Any

from fastapi import FastAPI, HTTPException

from app import db


logger = logging.getLogger("consumer.callback_api")

app = FastAPI(
    title="Maintenance Call Consumer Callback API",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/voice/callback")
def voice_callback(payload: dict[str, Any]) -> dict[str, Any]:
    logger.info("Received voice callback payload=%s", payload)

    correlation_id = payload.get("correlationId") or payload.get("correlation_id")

    if not correlation_id:
        raise HTTPException(
            status_code=400,
            detail="correlationId is required",
        )

    callback_payload_file_path = (
        payload.get("callbackPayloadFilePath")
        or payload.get("callback_payload_file_path")
    )

    if not callback_payload_file_path:
        raise HTTPException(
            status_code=400,
            detail="callbackPayloadFilePath is required",
        )

    conn = None

    try:
        conn = db.get_connection()

        job = db.get_job_by_correlation_id(
            conn,
            correlation_id=str(correlation_id),
        )

        if job is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No voice_bot_call_job found for "
                    f"correlationId={correlation_id}"
                ),
            )

        db.complete_call_from_callback(
            conn,
            job_id=int(job["id"]),
            callback_payload=payload,
            callback_payload_file_path=str(callback_payload_file_path),
        )

        logger.info(
            "Voice callback completed job_id=%s correlation_id=%s path=%s",
            job["id"],
            correlation_id,
            callback_payload_file_path,
        )

        return {
            "status": "received",
            "correlationId": str(correlation_id),
            "jobId": int(job["id"]),
            "callbackPayloadFilePath": str(callback_payload_file_path),
        }

    except HTTPException:
        if conn is not None:
            conn.rollback()
        raise

    except Exception as exc:
        if conn is not None:
            conn.rollback()

        logger.exception(
            "Failed processing voice callback correlation_id=%s",
            correlation_id,
        )

        raise HTTPException(
            status_code=500,
            detail=f"Callback processing failed: {exc}",
        ) from exc

    finally:
        if conn is not None:
            conn.close()