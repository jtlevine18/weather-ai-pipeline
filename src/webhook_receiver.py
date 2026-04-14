"""
Minimal FastAPI webhook receiver.

- POST /webhook        — accept a JSON payload, append to event log
- GET  /webhook/history — return the last 20 logged events
"""

import hashlib
import hmac
import json
import logging
import os
from collections import deque
from typing import Any

from fastapi import FastAPI, HTTPException, Request

log = logging.getLogger(__name__)

app = FastAPI(title="Weather Pipeline Webhook Receiver")

EVENTS_DIR = "events"
LOG_FILE = os.path.join(EVENTS_DIR, "webhook_log.jsonl")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
if not WEBHOOK_SECRET:
    log.warning(
        "WEBHOOK_SECRET not set — webhook endpoint will accept unauthenticated requests. "
        "Set WEBHOOK_SECRET in production."
    )


def _verify_hmac(body: bytes, signature: str) -> bool:
    """Constant-time HMAC-SHA256 comparison of request body against secret."""
    if not WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    # Accept either a raw hex digest or the common "sha256=<hex>" prefix.
    provided = signature.split("=", 1)[1] if signature.startswith("sha256=") else signature
    return hmac.compare_digest(expected, provided)


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Append the incoming JSON object as one line in the JSONL log.

    Requires an ``X-Webhook-Signature`` header containing the HMAC-SHA256
    of the raw request body keyed by ``WEBHOOK_SECRET``. If the secret is
    unset (local dev), signature checking is skipped but a warning was
    emitted at startup.
    """
    raw_body = await request.body()

    if WEBHOOK_SECRET:
        signature = request.headers.get("X-Webhook-Signature", "")
        if not _verify_hmac(raw_body, signature):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    os.makedirs(EVENTS_DIR, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(payload) + "\n")
    return {"status": "received"}


@app.get("/webhook/history")
async def webhook_history():
    """Return the last 20 webhook entries (most-recent last)."""
    if not os.path.exists(LOG_FILE):
        return {"events": []}
    with open(LOG_FILE, "r") as f:
        last_lines = deque(f, maxlen=20)
    recent = []
    for line in last_lines:
        line = line.strip()
        if line:
            recent.append(json.loads(line))
    return {"events": recent}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
