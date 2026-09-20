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
    logger.info(
        "Received Carexpotel voice callback payload=%s",
        payload,
    )

    correlation_id = payload.get("correlationId")
    response_data = payload.get("responseData")

    if not correlation_id:
        raise HTTPException(
            status_code=400,
            detail="correlationId is required",
        )

    if not isinstance(response_data, dict):
        raise HTTPException(
            status_code=400,
            detail="responseData must be an object",
        )

    conn = None

    try:
        conn = db.get_connection()

        job = db.get_job_by_correlation_id(
            conn,
            correlation_id=correlation_id,
        )

        if job is None:
            raise HTTPException(
                status_code=404,
                detail=f"No VoiceCallJob found for correlationId={correlation_id}",
            )

        db.mark_poc_completed(
            conn,
            job_id=int(job.job_id),
            result=payload,
        )

        logger.info(
            "VoiceCallJob completed from callback "
            "job_id=%s correlation_id=%s",
            job.job_id,
            correlation_id,
        )

        return {
            "status": "received",
            "correlationId": correlation_id,
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