# Carexpotel — ElevenLabs + Twilio Outbound Call POC

This version converts the original browser/WebRTC POC into the phone-call flow:

```text
Carexpotel
   ↓
POST /api/outbound-call
   ↓
ElevenLabs POST /v1/convai/twilio/outbound-call
   ↓
Twilio phone call
   ↓
ElevenLabs Agent
   ↓
Driver conversation
   ↓
ElevenLabs post_call_transcription webhook
   ↓
POST /api/webhooks/elevenlabs/post-call
   ↓
Transcript saved by Carexpotel
   ↓
POST /api/ai/extract (AI hand-off boundary)
```

The Publisher/Consumer services can call the same `POST /api/outbound-call` endpoint later. They are intentionally not included in this POC change.

## 1. ElevenLabs setup

You need one ElevenLabs Conversational AI agent.

Keep the dynamic variables used by the existing POC:

- `driver_name`
- `driver_phone`
- `car_number`
- `due_date`
- `depot_name`
- `correlation_id`

The agent prompt can continue to use:

```text
{{driver_name}}
{{car_number}}
{{due_date}}
{{depot_name}}
```

For example:

```text
Hello {{driver_name}}, this is the vehicle service team from XYZ Car Rental.
I am calling about vehicle {{car_number}}, which is due for its periodic service.
Can you tell me when you can bring the vehicle to {{depot_name}} for servicing?
```

## 2. Twilio / phone setup

Your ElevenLabs agent must already be connected to a Twilio-integrated ElevenLabs phone number.

You need the **ElevenLabs agent phone number ID**. This is different from the driver’s phone number.

- `ELEVENLABS_AGENT_ID` = the agent that handles the conversation.
- `ELEVENLABS_AGENT_PHONE_NUMBER_ID` = the ElevenLabs phone number that originates the call.
- `to_number` = the driver's phone number.

ElevenLabs documents the outbound endpoint as:

```http
POST https://api.elevenlabs.io/v1/convai/twilio/outbound-call
```

The request requires `agent_id`, `agent_phone_number_id`, and `to_number`; runtime dynamic variables are supplied through `conversation_initiation_client_data`. The response returns `conversation_id` and `callSid`.

## 3. Backend setup

PowerShell:

```powershell
cd E:\YOUR_PATH\elevenlabs_browser_car_service_poc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

Add these values:

```env
ELEVENLABS_API_KEY=YOUR_SERVER_SIDE_API_KEY
ELEVENLABS_AGENT_ID=agent_your_actual_id
ELEVENLABS_AGENT_PHONE_NUMBER_ID=YOUR_ELEVENLABS_PHONE_NUMBER_ID
```

You said you will add the `agent_id`; also add the phone-number ID and server-side ElevenLabs API key.

Start:

```powershell
uvicorn backend.main:app --reload --port 8000
```

Health:

```text
http://127.0.0.1:8000/health
```

## 4. Frontend setup

Open a second PowerShell:

```powershell
cd E:\YOUR_PATH\elevenlabs_browser_car_service_poc\frontend
npm install
npm run dev
```

Open the Vite URL, normally:

```text
http://localhost:5173
```

Click **Start outbound call**.

The browser now only acts as a test UI. It does NOT use a microphone and does NOT start an ElevenLabs WebRTC session.

## 5. What the backend sends to ElevenLabs

For a test call, the backend makes:

```http
POST https://api.elevenlabs.io/v1/convai/twilio/outbound-call
xi-api-key: YOUR_ELEVENLABS_API_KEY
Content-Type: application/json
```

Body:

```json
{
  "agent_id": "agent_xxx",
  "agent_phone_number_id": "phone_xxx",
  "to_number": "+919876543210",
  "conversation_initiation_client_data": {
    "dynamic_variables": {
      "driver_name": "Rahul Kumar",
      "driver_phone": "+919876543210",
      "car_number": "KA01AB1238",
      "due_date": "2026-09-15",
      "depot_name": "Bangalore Central Depot",
      "correlation_id": "MAINT-10001"
    }
  }
}
```

The backend stores the returned `conversation_id` and `callSid`.

## 6. Post-call webhook

Create/configure an ElevenLabs webhook listening for:

```text
post_call_transcription
```

Point it to:

```text
https://YOUR_PUBLIC_HOST/api/webhooks/elevenlabs/post-call
```

For local development, the webhook URL must be publicly reachable. A tunnel such as ngrok or Cloudflare Tunnel is appropriate for the test environment.

The backend validates the `ElevenLabs-Signature` header when `ELEVENLABS_WEBHOOK_SECRET` is configured.

The webhook endpoint saves:

- conversation ID
- Twilio Call SID when available
- driver information from dynamic variables
- car number
- due date
- depot
- correlation ID
- full transcript
- transcript text
- ElevenLabs analysis
- metadata

The call is saved as:

```text
calls/<car-number>_<correlation-id>.json
```

That avoids overwriting previous calls for the same vehicle.

## 7. Transcript → AI

The endpoint:

```http
POST /api/ai/extract
```

is the explicit hand-off boundary for the next stage.

It currently receives the authoritative ElevenLabs transcript and returns the normalized text plus the expected extraction schema:

```json
{
  "confirmed": true,
  "appointment_date": "YYYY-MM-DD",
  "appointment_time": "HH:MM"
}
```

The ElevenLabs/Twilio call and authoritative transcript path are complete before adding an AI provider.

## 8. Production integration point for your Consumer Worker

Once this POC works, your Consumer Worker does not need to know about Twilio internals.

It can call:

```http
POST /api/outbound-call
```

with:

```json
{
  "driver_name": "...",
  "driver_phone": "...",
  "car_number": "...",
  "due_date": "...",
  "depot_name": "...",
  "correlation_id": "..."
}
```

Carexpotel then owns:

```text
Consumer
  ↓
Carexpotel /api/outbound-call
  ↓
ElevenLabs
  ↓
Twilio
  ↓
Driver
  ↓
ElevenLabs
  ↓
Carexpotel webhook
```

## Important

Do not put `ELEVENLABS_API_KEY` in frontend JavaScript.

The current browser ElevenLabs SDK code has been removed from this test because the production phone call should be initiated server-side through the ElevenLabs Twilio outbound endpoint.
