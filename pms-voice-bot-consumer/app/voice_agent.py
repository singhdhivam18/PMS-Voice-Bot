from typing import Any
import logging

import httpx

from app.config import config


logger = logging.getLogger("consumer.voice_agent")


class VoiceAgentError(RuntimeError):
    pass


class VoiceAgent:

    def trigger_call(
        self,
        *,
        correlation_id: str,
        idempotency_key: str,
        service_id: int,
        carno: str,
        driver_name: str,
        driver_phone: str,
        due_maintenance_date: str,
        maintenance_type: str,
    ) -> dict[str, Any]:

        payload = {
            "driver_name": driver_name,
            "driver_phone": driver_phone,
            "car_number": carno,
            "due_date": due_maintenance_date,
            "depot_name": config.VOICE_AGENT_DEPOT_NAME,
            "correlation_id": correlation_id,
            "callback_url": config.VOICE_AGENT_CALLBACK_URL,

            "service_id": service_id,
            "idempotency_key": idempotency_key,
            "maintenance_type": maintenance_type,
        }

        url = (
            config.VOICE_AGENT_BASE_URL.rstrip("/")
            + "/api/outbound-call"
        )

        logger.info(
            "Starting Voice Agent outbound call "
            "correlation_id=%s idempotency_key=%s url=%s",
            correlation_id,
            idempotency_key,
            url,
        )

        try:
            response = httpx.post(
                url,
                json=payload,
                timeout=config.VOICE_AGENT_TIMEOUT,
            )

        except httpx.ConnectError as exc:
            logger.exception(
                "Could not connect to Carexpotel Voice Agent url=%s",
                url,
            )
            raise VoiceAgentError(
                f"Could not connect to Carexpotel at {url}"
            ) from exc

        except httpx.TimeoutException as exc:
            logger.exception(
                "Carexpotel request timed out url=%s timeout=%s",
                url,
                config.VOICE_AGENT_TIMEOUT,
            )
            raise VoiceAgentError(
                "Voice Agent API request timed out"
            ) from exc

        except httpx.HTTPError as exc:
            logger.exception(
                "Carexpotel HTTP request failed url=%s",
                url,
            )
            raise VoiceAgentError(
                f"Voice Agent API request failed: {exc}"
            ) from exc

        logger.info(
            "Carexpotel response status=%s correlation_id=%s",
            response.status_code,
            correlation_id,
        )

        try:
            result = response.json()

        except ValueError as exc:
            logger.error(
                "Carexpotel returned non-JSON response: %s",
                response.text,
            )
            raise VoiceAgentError(
                "Voice Agent API returned invalid JSON"
            ) from exc

        logger.info(
            "Carexpotel response body=%s",
            result,
        )

        if response.status_code >= 400:
            raise VoiceAgentError(
                f"Voice Agent API returned HTTP "
                f"{response.status_code}: {result}"
            )

        status = str(
            result.get("status") or ""
        ).strip().lower()

        if status != "call_initiated":
            raise VoiceAgentError(
                f"Voice Agent call was not initiated: {result}"
            )

        logger.info(
            "Voice Agent call initiated successfully "
            "correlation_id=%s conversation_id=%s",
            correlation_id,
            result.get("conversation_id"),
        )

        return result


voice_agent = VoiceAgent()