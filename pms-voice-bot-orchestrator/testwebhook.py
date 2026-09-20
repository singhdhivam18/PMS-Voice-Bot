import hashlib
import hmac
import json
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_SECRET = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()

if not WEBHOOK_SECRET:
    raise RuntimeError("ELEVENLABS_WEBHOOK_SECRET is missing from .env")


WEBHOOK_URL = (
    "https://footwear-repave-apache.ngrok-free.dev"
    "/api/webhooks/elevenlabs/post-call"
)


payload = {
    "type": "post_call_transcription",
    "event_timestamp": int(time.time()),
    "data": {
        "conversation_id": "conv_9101m27sdefcewxabt8rbbdebj5r",
        "status": "done",

        "transcript": [
            {
                "role": "agent",
                "message": (
                    "Hi Dheeraj This is an automated reminder that your car "
                    "KA41MD5457 is due for periodic maintenance service on "
                    "15-September-2026. Would you like to book an appointment?"
                ),
            },
            {
                "role": "user",
                "message": "Yes.",
            },
            {
                "role": "agent",
                "message": (
                    "Great, I can help you schedule that appointment. "
                    "Please let me know which date and time works best for "
                    "you to bring the car in."
                ),
            },
            {
                "role": "user",
                "message": "I prefer Kannada.",
            },
            {
                "role": "agent",
                "message": (
                    "Thank you for letting me know, I will switch to Kannada "
                    "for the rest of our conversation."
                ),
            },
            {
                "role": "user",
                "message": "13th September.",
            },
            {
                "role": "agent",
                "message": (
                    "September thirteenth has already passed. "
                    "Could you please provide a future date and time?"
                ),
            },
            {
                "role": "user",
                "message": "Okay. Can you schedule it on sixteenth September?",
            },
            {
                "role": "agent",
                "message": (
                    "Yes, I can schedule your appointment for September "
                    "sixteenth. Please let me know what time."
                ),
            },
            {
                "role": "user",
                "message": "2:00 PM in the afternoon.",
            },
            {
                "role": "agent",
                "message": (
                    "Perfect, I have scheduled your periodic maintenance "
                    "service for September sixteenth at two in the afternoon."
                ),
            },
            {
                "role": "user",
                "message": "Not really. Thank you.",
            },
            {
                "role": "agent",
                "message": (
                    "You are very welcome, and thank you for confirming "
                    "your appointment. Goodbye!"
                ),
            },
        ],

        "analysis": {},

        "metadata": {
            "phone_call": {
                "call_sid": "CA9f51d3543d03ea36f12680888792cf50"
            }
        },

        "conversation_initiation_client_data": {
            "dynamic_variables": {
                "Driver_Name": "Dheeraj",
                "Car_Registration_Number": "KA41MD5457",
                "Due_date": "15-September-2026",
                "driver_phone": "+918884319959",
                "depot_name": "Bangalore Central Depot",
                "correlation_id": "svc-demo-001",
            }
        },
    },
}


raw_body = json.dumps(
    payload,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")

timestamp = str(int(time.time()))

signed_payload = f"{timestamp}.".encode("utf-8") + raw_body

signature = hmac.new(
    WEBHOOK_SECRET.encode("utf-8"),
    signed_payload,
    hashlib.sha256,
).hexdigest()

headers = {
    "Content-Type": "application/json",
    "ElevenLabs-Signature": f"t={timestamp},v0={signature}",
}

print("Sending webhook replay...")
print("URL:", WEBHOOK_URL)

response = httpx.post(
    WEBHOOK_URL,
    content=raw_body,
    headers=headers,
    timeout=30,
)

print("\nHTTP STATUS:", response.status_code)
print("RESPONSE:")
print(response.text)