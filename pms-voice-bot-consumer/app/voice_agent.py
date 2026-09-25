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
        service_id: int,
        registration_no: str,
        driver_name: str,
        driver_phone: str,
        due_maintenance_date: str,
        maintenance_type: str,
        preferred_language:str,
    ) -> dict[str, Any]:
        payload = {
            "driver_name": driver_name,
            "driver_phone": driver_phone,
            "car_number": registration_no,
            "due_date": due_maintenance_date,
            "depot_name": config.VOICE_AGENT_DEPOT_NAME,
            "correlation_id": correlation_id,
            "callback_url": config.VOICE_AGENT_CALLBACK_URL,
            "service_id": service_id,
            "maintenance_type": maintenance_type,
            "preferred_language":preferred_language,
        }

        url = (
            config.VOICE_AGENT_BASE_URL.rstrip("/")
            + "/api/outbound-call"
        )

        logger.info(
            "Starting Voice Agent outbound call "
            "correlation_id=%s service_id=%s url=%s",
            correlation_id,
            service_id,
            url,
        )

        try:
            response = httpx.post(
                url,
                json=payload,
                timeout=config.VOICE_AGENT_TIMEOUT,
            )
        except httpx.ConnectError as exc:
            logger.exception("Could not connect to Voice Agent url=%s", url)
            raise VoiceAgentError(
                f"Could not connect to Voice Agent at {url}"
            ) from exc
        except httpx.TimeoutException as exc:
            logger.exception(
                "Voice Agent request timed out url=%s timeout=%s",
                url,
                config.VOICE_AGENT_TIMEOUT,
            )
            raise VoiceAgentError(
                "Voice Agent API request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            logger.exception("Voice Agent HTTP request failed url=%s", url)
            raise VoiceAgentError(
                f"Voice Agent API request failed: {exc}"
            ) from exc

        logger.info(
            "Voice Agent response status=%s correlation_id=%s",
            response.status_code,
            correlation_id,
        )

        try:
            result = response.json()
        except ValueError as exc:
            logger.error("Voice Agent returned non-JSON response: %s", response.text)
            raise VoiceAgentError(
                "Voice Agent API returned invalid JSON"
            ) from exc

        if response.status_code >= 400:
            raise VoiceAgentError(
                f"Voice Agent API returned HTTP {response.status_code}: {result}"
            )

        status = str(result.get("status") or "").strip().lower()
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
