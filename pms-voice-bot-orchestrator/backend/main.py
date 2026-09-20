import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CALLS_DIR = BASE_DIR / "calls"
CALLS_DIR.mkdir(parents=True, exist_ok=True)

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
ELEVENLABS_OUTBOUND_PATH = "/v1/convai/twilio/outbound-call"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("carexpotel-elevenlabs")

app = FastAPI(
    title="Carexpotel ElevenLabs + Twilio Voice Integration",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULTS = {
    "driver_name": os.getenv("TEST_DRIVER_NAME", "Shivam"),
    "driver_phone": os.getenv("TEST_DRIVER_PHONE", "+919980014906"),
    "car_number": os.getenv("TEST_CAR_NUMBER", "KA01AB1238"),
    "due_date": os.getenv("TEST_DUE_DATE", "15-September-2026"),
    "depot_name": os.getenv("TEST_DEPOT_NAME", "Bangalore Central Depot"),
    "correlation_id": os.getenv("TEST_CORRELATION_ID", "svc-demo-001"),
}

class OutboundCallRequest(BaseModel):
    driver_name: str = Field(min_length=1)
    driver_phone: str = Field(min_length=5)
    car_number: str = Field(min_length=1)
    due_date: str = Field(min_length=1)
    depot_name: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    callback_url: str | None = None

    service_id: int | None = None
    idempotency_key: str | None = None
    maintenance_type: str | None = None

class AIExtractionRequest(BaseModel):
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str = Field(min_length=1)
    driver_name: str = Field(min_length=1)
    car_number: str = Field(min_length=1)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_car_number(value: str) -> str:
    safe = "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid car_number")
    return safe

def call_file_path(car_number: str, correlation_id: str | None = None) -> Path:
    safe_car = safe_car_number(car_number)
    if correlation_id:
        safe_corr = "".join(
            ch for ch in correlation_id if ch.isalnum() or ch in ("-", "_")
        )
        if safe_corr:
            return CALLS_DIR / f"{safe_car}_{safe_corr}.json"
    return CALLS_DIR / f"{safe_car}.json"

def elevenlabs_headers() -> dict[str, str]:
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ELEVENLABS_API_KEY is missing from backend .env",
        )
    return {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }

def get_dynamic(dynamic_variables: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first present dynamic variable key. ElevenLabs names are case-sensitive."""
    for key in keys:
        if key in dynamic_variables and dynamic_variables[key] not in (None, ""):
            return dynamic_variables[key]
    return default

def verify_elevenlabs_signature(
    raw_body: bytes,
    signature: str | None,
) -> bool:
    secret = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()

    if not secret:
        logger.error("WEBHOOK DEBUG: secret is missing")
        return False

    if not signature:
        logger.error("WEBHOOK DEBUG: ElevenLabs-Signature header is missing")
        return False

    try:
        parts: dict[str, str] = {}

        for item in signature.split(","):
            key, value = item.split("=", 1)
            parts[key.strip()] = value.strip()

        timestamp = parts.get("t")
        received_signature = parts.get("v0")

        if not timestamp:
            logger.error("WEBHOOK DEBUG: timestamp missing")
            return False

        if not received_signature:
            logger.error("WEBHOOK DEBUG: v0 signature missing")
            return False

        max_age = int(
            os.getenv("ELEVENLABS_WEBHOOK_MAX_AGE_SECONDS", "1800")
        )

        age = abs(int(time.time()) - int(timestamp))

        logger.info(
            "WEBHOOK DEBUG: timestamp_age=%s max_age=%s",
            age,
            max_age,
        )

        if age > max_age:
            logger.error(
                "WEBHOOK DEBUG: timestamp too old age=%s max_age=%s",
                age,
                max_age,
            )
            return False

        signed_payload = (
            f"{timestamp}.".encode("utf-8") + raw_body
        )

        expected = hmac.new(
            secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        matches = hmac.compare_digest(
            expected,
            received_signature,
        )

        logger.info(
            "WEBHOOK DEBUG: HMAC matches=%s body_bytes=%s",
            matches,
            len(raw_body),
        )

        return matches

    except Exception:
        logger.exception(
            "WEBHOOK DEBUG: exception while verifying signature"
        )
        return False
def transcript_to_text(transcript: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for turn in transcript:
        role = str(turn.get("role") or turn.get("source") or "unknown").strip()
        message = str(
            turn.get("message")
            or turn.get("text")
            or turn.get("content")
            or ""
        ).strip()
        if message:
            speaker = "Driver" if role.lower() in {"user", "driver"} else "Agent"
            lines.append(f"{speaker}: {message}")
    return "\n".join(lines)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "agent_id": os.getenv("ELEVENLABS_AGENT_ID", "").strip(),
        "agent_id_configured": bool(os.getenv("ELEVENLABS_AGENT_ID", "").strip()),
        "agent_phone_number_id_configured": bool(
            os.getenv("ELEVENLABS_AGENT_PHONE_NUMBER_ID", "").strip()
        ),
        "webhook_secret_configured": bool(
            os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()
        ),
        "defaults": DEFAULTS,
    }

@app.post("/api/outbound-call")
async def outbound_call(request: OutboundCallRequest) -> dict[str, Any]:
    """Start the real outbound phone call through ElevenLabs' Twilio integration."""
    agent_id = os.getenv("ELEVENLABS_AGENT_ID", "").strip()
    agent_phone_number_id = os.getenv("ELEVENLABS_AGENT_PHONE_NUMBER_ID", "").strip()

    if not agent_id:
        raise HTTPException(status_code=500, detail="ELEVENLABS_AGENT_ID is missing")
    if not agent_phone_number_id:
        raise HTTPException(
            status_code=500,
            detail="ELEVENLABS_AGENT_PHONE_NUMBER_ID is missing",
        )

    # These names intentionally match the existing ElevenLabs agent placeholders.
    # ElevenLabs dynamic variable names are case-sensitive.
    dynamic_variables = {
        "Driver_Name": request.driver_name,
        "Car_Registration_Number": request.car_number,
        "Due_date": request.due_date,
        "driver_phone": request.driver_phone,
        "depot_name": request.depot_name,
        "correlation_id": request.correlation_id,
    }

    payload = {
        "agent_id": agent_id,
        "agent_phone_number_id": agent_phone_number_id,
        "to_number": request.driver_phone,
        "conversation_initiation_client_data": {
            "dynamic_variables": dynamic_variables,
        },
        "call_recording_enabled": os.getenv(
            "ELEVENLABS_CALL_RECORDING_ENABLED", "false"
        ).lower() == "true",
    }

    path = call_file_path(request.car_number, request.correlation_id)
    initial_record = {
        "status": "call_requested",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        **request.model_dump(),
        "conversation_id": None,
        "twilio_call_sid": None,
        "transcript": [],
        "analysis": None,
    }
    path.write_text(
        json.dumps(initial_record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ELEVENLABS_BASE_URL + ELEVENLABS_OUTBOUND_PATH,
                headers=elevenlabs_headers(),
                json=payload,
            )
    except httpx.HTTPError as exc:
        initial_record["status"] = "call_request_failed"
        initial_record["updated_at"] = utc_now()
        initial_record["error"] = str(exc)
        path.write_text(
            json.dumps(initial_record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach ElevenLabs: {exc}",
        ) from exc

    if response.status_code >= 400:
        initial_record["status"] = "call_request_failed"
        initial_record["updated_at"] = utc_now()
        initial_record["elevenlabs_response"] = response.text
        path.write_text(
            json.dumps(initial_record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        raise HTTPException(
            status_code=502,
            detail=f"ElevenLabs outbound call failed ({response.status_code}): {response.text}",
        )

    result = response.json()
    initial_record.update(
        {
            "status": "call_initiated",
            "updated_at": utc_now(),
            "conversation_id": result.get("conversation_id"),
            "twilio_call_sid": result.get("callSid"),
            "elevenlabs_message": result.get("message"),
        }
    )
    path.write_text(
        json.dumps(initial_record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "Outbound call initiated correlation_id=%s conversation_id=%s callSid=%s",
        request.correlation_id,
        result.get("conversation_id"),
        result.get("callSid"),
    )

    return {
        "status": "call_initiated",
        "conversation_id": result.get("conversation_id"),
        "callSid": result.get("callSid"),
        "message": result.get("message"),
        "correlation_id": request.correlation_id,
    }

@app.post("/api/webhooks/elevenlabs/post-call")
async def elevenlabs_post_call(
    request: Request,
    elevenlabs_signature: str | None = Header(
        default=None,
        alias="ElevenLabs-Signature",
    ),
) -> dict[str, Any]:
    """
    Receives ElevenLabs post_call_transcription events.

    The endpoint intentionally returns quickly after persisting the event.
    AI extraction can be triggered after persistence.
    """
    raw_body = await request.body()

    logger.info(
        "WEBHOOK DEBUG: request received signature_present=%s body_bytes=%s",
        bool(elevenlabs_signature),
        len(raw_body),
    )

    if not verify_elevenlabs_signature(raw_body, elevenlabs_signature):
        raise HTTPException(status_code=401, detail="Invalid ElevenLabs webhook signature")

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload") from exc

    if event.get("type") != "post_call_transcription":
        # Keep the endpoint forward-compatible with other ElevenLabs webhook events.
        return {
            "status": "ignored",
            "event_type": event.get("type"),
        }

    data = event.get("data") or {}
    conversation_id = data.get("conversation_id")
    transcript = data.get("transcript") or []
    analysis = data.get("analysis")

    # ElevenLabs Data Collection results can be included in the post-call analysis.
    # Keep a normalized copy for the later AI/business-processing stage.
    extracted_data = {}
    if isinstance(analysis, dict):
        candidate = analysis.get("data_collection") or analysis.get("dataCollection") or {}
        if isinstance(candidate, dict):
            extracted_data = candidate

    initiation = data.get("conversation_initiation_client_data") or {}
    dynamic_variables = initiation.get("dynamic_variables") or {}

    driver_name = get_dynamic(dynamic_variables, "Driver_Name", "driver_name")
    driver_phone = get_dynamic(dynamic_variables, "driver_phone", default=None)
    car_number = get_dynamic(
        dynamic_variables,
        "Car_Registration_Number",
        "car_number",
        default=data.get("metadata", {}).get("phone_call", {}).get("car_number") or "unknown-car",
    )
    due_date = get_dynamic(dynamic_variables, "Due_date", "due_date", default=None)
    correlation_id = get_dynamic(dynamic_variables, "correlation_id", default=None)

    path = call_file_path(str(car_number), correlation_id)

    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Existing call file was invalid JSON: %s", path)

    payload = {
        **existing,
        "status": data.get("status", "completed"),
        "updated_at": utc_now(),
        "event_timestamp": event.get("event_timestamp"),
        "event_type": event.get("type"),
        "conversation_id": conversation_id or existing.get("conversation_id"),
        "twilio_call_sid": existing.get("twilio_call_sid")
        or data.get("metadata", {}).get("phone_call", {}).get("call_sid"),
        "driver_name": driver_name or existing.get("driver_name"),
        "driver_phone": driver_phone or existing.get("driver_phone"),
        "car_number": car_number or existing.get("car_number"),
        "due_date": due_date or existing.get("due_date"),
        "depot_name": get_dynamic(dynamic_variables, "depot_name", "Depot_Name", default=existing.get("depot_name")),
        "correlation_id": correlation_id or existing.get("correlation_id"),
        "transcript": transcript,
        "transcript_text": transcript_to_text(transcript),
        "analysis": analysis,
        "extracted_data": extracted_data,
        "metadata": data.get("metadata"),
        "conversation_initiation_client_data": initiation,
    }
    ai_result = None
    final_response = None
    callback_result = None

    # Convert ElevenLabs transcript into text before Gemini processing
    transcript_text = transcript_to_text(transcript)

    try:
        if transcript_text.strip():
            ai_result = await call_gemini_for_appointment(
                transcript_text=transcript_text,
                driver_name=str(
                    driver_name or existing.get("driver_name") or ""
                ),
                vehicle_registration_number=str(
                    car_number or existing.get("car_number") or ""
                ),
            )

            final_response = {
                "correlationId": correlation_id or existing.get("correlation_id"),
                "responseData": {
                    "driverName": ai_result.get(
                        "driverName",
                        driver_name or existing.get("driver_name"),
                    ),
                    "vehicleRegistrationNumber": ai_result.get(
                        "vehicleRegistrationNumber",
                        car_number or existing.get("car_number"),
                    ),
                    "confirmed": ai_result.get("confirmed", False),
                    "appointmentDate": ai_result.get(
                        "appointmentDate",
                        "",
                    ),
                    "appointmentTime": ai_result.get(
                        "appointmentTime",
                        "",
                    ),
                },
            }

            payload["ai_extraction"] = ai_result
            payload["final_response"] = final_response

            callback_url = (
                existing.get("callback_url")
                or os.getenv("CALLBACK_URL", "").strip()
                or None
            )

            callback_result = await send_consumer_callback(
                callback_url=callback_url,
                final_response=final_response,
            )

            payload["callback_url"] = callback_url
            payload["callback_result"] = callback_result

    except HTTPException as exc:
        logger.exception(
            "AI extraction failed conversation_id=%s",
            conversation_id,
        )
        payload["ai_extraction"] = None
        payload["ai_error"] = exc.detail
    # Prevent accidental overwrite of a different car when dynamic variables are absent.
    if path.name == "unknown-car.json":
        path = CALLS_DIR / f"conversation_{conversation_id or 'unknown'}.json"

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "Saved post-call transcript conversation_id=%s -> %s",
        conversation_id,
        path,
    )

    return {
        "status": "received",
        "conversation_id": conversation_id,
        "saved_file": path.name,
        "transcript_turns": len(transcript),
        "ai_extracted": ai_result is not None,
        "callback_status": (
            callback_result.get("status")
            if callback_result
            else "not_configured"
        ),
    }

@app.get("/api/calls/{correlation_id}")
def get_call(correlation_id: str) -> dict[str, Any]:
    # Search the small POC directory by the persisted business correlation id.
    for path in CALLS_DIR.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if record.get("correlation_id") == correlation_id:
            return record
    raise HTTPException(status_code=404, detail="Call not found")

@app.post("/api/ai/extract")
async def extract_appointment(
    request: AIExtractionRequest
) -> dict[str, Any]:

    transcript_text = transcript_to_text(request.transcript)

    if not transcript_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Transcript is empty"
        )

    ai_result = await call_gemini_for_appointment(
        transcript_text=transcript_text,
        driver_name=request.driver_name,
        vehicle_registration_number=request.car_number,
    )

    final_response = {
    "correlationId": request.correlation_id,
    "responseData": {
        "driverName": ai_result.get(
            "driverName",
            request.driver_name,
        ),
        "vehicleRegistrationNumber": ai_result.get(
            "vehicleRegistrationNumber",
            request.car_number,
        ),
        "confirmed": ai_result.get("confirmed", False),
        "appointmentDate": ai_result.get("appointmentDate", ""),
        "appointmentTime": ai_result.get("appointmentTime", ""),
         }
    }

    return final_response

@app.get("/api/conversations/{car_number}")
def get_latest_conversation(car_number: str) -> dict[str, Any]:
    safe_car = safe_car_number(car_number)
    matches = sorted(
        CALLS_DIR.glob(f"{safe_car}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if matches:
        return json.loads(matches[0].read_text(encoding="utf-8"))

    path = CALLS_DIR / f"{safe_car}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")
    return json.loads(path.read_text(encoding="utf-8"))

async def call_gemini_for_appointment(
    transcript_text: str,
    driver_name: str,
    vehicle_registration_number: str,
) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is missing from backend .env",
        )

    prompt = f"""
    You are an appointment extraction service.

    Current date: 2026-09-11

    Extract the FINAL CONFIRMED maintenance appointment from the conversation.

    Known information:
    Driver name: {driver_name}
    Vehicle registration: {vehicle_registration_number}

    Rules:
    1. Use the FINAL date and time that the driver actually confirms.
    2. Ignore the vehicle maintenance due date when determining the appointment.
    3. Return appointmentDate in YYYY-MM-DD format.
    4. Return appointmentTime in 24-hour HH:MM format.
    5. If the driver gives a date without a year, infer the year from the current date.
    6. For example, with current date 2026-09-11, "16th September"
    means 2026-09-16.
    7. Do not invent a date or time.
    8. If no appointment is confirmed, set confirmed=false.
    9. If confirmed=false, appointmentDate and appointmentTime must be empty strings.
    10. Return only JSON.

    Conversation:{transcript_text}"""

    response_schema = {
    "type": "OBJECT",
    "properties": {
        "driverName": {
            "type": "STRING",
            "description": "Driver's name"
        },
        "vehicleRegistrationNumber": {
            "type": "STRING",
            "description": "Vehicle registration number"
        },
        "confirmed": {
            "type": "BOOLEAN",
            "description": "Whether the driver finally confirmed an appointment"
        },
        "appointmentDate": {
            "type": "STRING",
            "description": "Confirmed appointment date in YYYY-MM-DD format; empty string when not confirmed"
        },
        "appointmentTime": {
            "type": "STRING",
            "description": "Confirmed appointment time in HH:MM 24-hour format; empty string when not confirmed"
        }
    },
    "required": [
        "driverName",
        "vehicleRegistrationNumber",
        "confirmed",
        "appointmentDate",
        "appointmentTime"
    ]
}
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": response_schema
        }
    }

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Gemini: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini extraction failed ({response.status_code}): {response.text}"
        )

    result = response.json()

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        extracted = json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected Gemini response: {result}"
        ) from exc

    return extracted
async def send_consumer_callback(
    callback_url: str | None,
    final_response: dict[str, Any],
) -> dict[str, Any] | None:

    if not callback_url:
        logger.info(
            "No consumer callback URL configured; "
            "final response will only be stored."
        )
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                callback_url,
                json=final_response,
                headers={
                    "Content-Type": "application/json",
                },
            )

        logger.info(
            "Consumer callback response status=%s url=%s",
            response.status_code,
            callback_url,
        )

        if response.status_code >= 400:
            return {
                "status": "failed",
                "http_status": response.status_code,
                "response": response.text,
            }

        return {
            "status": "sent",
            "http_status": response.status_code,
            "response": response.text,
        }

    except httpx.HTTPError as exc:
        logger.exception(
            "Consumer callback failed url=%s",
            callback_url,
        )

        return {
            "status": "failed",
            "error": str(exc),
        }
@app.post("/api/voice/callback")
async def voice_callback_proxy(request: Request):
    payload = await request.json()

    consumer_callback_url = (
        os.getenv(
            "CONSUMER_CALLBACK_INTERNAL_URL",
            "http://127.0.0.1:9000/api/voice/callback",
        )
        .strip()
    )

    logger.info(
        "Forwarding voice callback to Consumer: %s",
        consumer_callback_url,
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                consumer_callback_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                },
            )

        logger.info(
            "Consumer callback response status=%s",
            response.status_code,
        )

    except httpx.HTTPError as exc:
        logger.exception(
            "Failed to forward voice callback to Consumer"
        )

        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Consumer callback: {exc}",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Consumer callback failed "
                f"({response.status_code}): {response.text}"
            ),
        )

    return {
        "status": "forwarded",
        "consumer_status": response.status_code,
    }