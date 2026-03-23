"""
Minimal FastAPI webhook receiver.

- POST /webhook        — accept a JSON payload, append to event log
- GET  /webhook/history — return the last 20 logged events
"""

import json
import os
from collections import deque
from typing import Any

from fastapi import FastAPI

app = FastAPI(title="Weather Pipeline Webhook Receiver")

EVENTS_DIR = "events"
LOG_FILE = os.path.join(EVENTS_DIR, "webhook_log.jsonl")


@app.post("/webhook")
async def receive_webhook(payload: dict[str, Any]):
    """Append the incoming JSON object as one line in the JSONL log."""
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
