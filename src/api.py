"""Unified REST API for the weather pipeline.

Consolidates health, webhook, and data endpoints into a single FastAPI app.
Run with: python run_api.py (or: uvicorn src.api:app --reload)
"""

from __future__ import annotations
import json
import os
import uuid
from dotenv import load_dotenv
load_dotenv()
from collections import deque
from typing import Any, Dict, List

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.auth import get_current_user, require_operator, User, create_token, verify_password, hash_password
from src.health import get_health_status

app = FastAPI(
    title="Weather Pipeline API",
    version="1.0.0",
    description="REST API for the Kerala/Tamil Nadu agricultural weather pipeline",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health (public)
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Pipeline health check — no auth required."""
    return get_health_status()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/auth/token")
def login(username: str, password: str):
    """Exchange username + password for a JWT token."""
    from src.database import init_db
    conn = init_db()
    row = conn.execute(
        "SELECT id, password_hash, role FROM users WHERE username = ?",
        [username],
    ).fetchone()
    if row is None or not verify_password(password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(username, row[2])
    return {"access_token": token, "token_type": "bearer", "role": row[2]}


@app.post("/auth/bootstrap", status_code=201)
def bootstrap_admin(username: str, password: str):
    """Create the first admin user. Only works when no users exist yet."""
    from src.database import init_db
    conn = init_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0:
        raise HTTPException(status_code=409, detail="Users already exist — use /auth/token")
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role) VALUES (?,?,?,?)",
        [str(uuid.uuid4()), username, hash_password(password), "operator"],
    )
    token = create_token(username, "operator")
    return {"access_token": token, "token_type": "bearer", "role": "operator"}


@app.post("/auth/register", status_code=201)
def register(username: str, password: str, role: str = "viewer",
             operator: User = Depends(require_operator)):
    """Create a new user (operator-only)."""
    from src.database import init_db
    conn = init_db()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role) VALUES (?,?,?,?)",
        [str(uuid.uuid4()), username, hash_password(password), role],
    )
    return {"username": username, "role": role}


# ---------------------------------------------------------------------------
# Data endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/stations")
def list_stations(user: User = Depends(get_current_user)):
    """List all 20 weather stations."""
    from config import STATIONS
    return [
        {"id": s.station_id, "name": s.name, "lat": s.lat, "lon": s.lon,
         "state": s.state, "altitude_m": s.altitude_m}
        for s in STATIONS
    ]


@app.get("/api/forecasts")
def get_forecasts(limit: int = Query(50, le=500),
                  forecast_day: int = Query(None, ge=0, le=6),
                  user: User = Depends(get_current_user)):
    """Recent forecasts across all stations. Optional forecast_day filter (0-6)."""
    from src.database import init_db, get_recent_forecasts
    conn = init_db()
    results = get_recent_forecasts(conn, limit=limit)
    if forecast_day is not None:
        results = [r for r in results if r.get("forecast_day", 0) == forecast_day]
    return results


@app.get("/api/alerts")
def get_alerts(limit: int = Query(50, le=200),
               user: User = Depends(get_current_user)):
    """Recent agricultural alerts / advisories."""
    from src.database import init_db, get_recent_alerts
    conn = init_db()
    return get_recent_alerts(conn, limit=limit)


@app.get("/api/station/{station_id}/latest")
def station_latest(station_id: str,
                   user: User = Depends(get_current_user)):
    """Latest clean telemetry for a station."""
    from src.database import init_db, get_latest_clean_for_station
    conn = init_db()
    result = get_latest_clean_for_station(conn, station_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {station_id}")
    return result


@app.get("/api/pipeline/runs")
def pipeline_runs(limit: int = Query(10, le=50),
                  user: User = Depends(get_current_user)):
    """Recent pipeline run history."""
    from src.database import init_db
    from src.database._util import _rows_to_dicts
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


# ---------------------------------------------------------------------------
# Webhook (public)
# ---------------------------------------------------------------------------

EVENTS_DIR = "events"
LOG_FILE = os.path.join(EVENTS_DIR, "webhook_log.jsonl")


@app.post("/webhook")
async def receive_webhook(payload: dict):
    """Accept a JSON payload and append to event log."""
    os.makedirs(EVENTS_DIR, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(payload) + "\n")
    return {"status": "received"}


@app.get("/webhook/history")
async def webhook_history():
    """Return the last 20 webhook entries."""
    if not os.path.exists(LOG_FILE):
        return {"events": []}
    with open(LOG_FILE, "r") as f:
        last_lines = deque(f, maxlen=20)
    return {"events": [json.loads(ln.strip()) for ln in last_lines if ln.strip()]}
