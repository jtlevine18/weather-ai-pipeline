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

from fastapi import FastAPI, Depends, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from prometheus_fastapi_instrumentator import Instrumentator

from src.auth import get_current_user, require_operator, User, create_token, verify_password, hash_password
from src.health import get_health_status

app = FastAPI(
    title="Weather Pipeline API",
    version="1.0.0",
    description="REST API for the Kerala/Tamil Nadu agricultural weather pipeline",
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS — locked to known origins
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://jtlevine-ai-weather-pipeline.hf.space",
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8501",  # Streamlit
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

Instrumentator().instrument(app).expose(app)

# ---------------------------------------------------------------------------
# Webhook secret
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


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
@limiter.limit("5/minute")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
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
@limiter.limit("3/minute")
def bootstrap_admin(request: Request, username: str, password: str):
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
@limiter.limit("5/minute")
def register(request: Request, username: str, password: str, role: str = "viewer",
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
@limiter.limit("60/minute")
def list_stations(request: Request, user: User = Depends(get_current_user)):
    """List all 20 weather stations."""
    from config import STATIONS
    return [
        {"id": s.station_id, "name": s.name, "lat": s.lat, "lon": s.lon,
         "state": s.state, "altitude_m": s.altitude_m}
        for s in STATIONS
    ]


@app.get("/api/forecasts")
@limiter.limit("60/minute")
def get_forecasts(request: Request, limit: int = Query(50, le=500),
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
@limiter.limit("60/minute")
def get_alerts(request: Request, limit: int = Query(50, le=200),
               user: User = Depends(get_current_user)):
    """Recent agricultural alerts / advisories."""
    from src.database import init_db, get_recent_alerts
    conn = init_db()
    return get_recent_alerts(conn, limit=limit)


@app.get("/api/station/{station_id}/latest")
@limiter.limit("60/minute")
def station_latest(request: Request, station_id: str,
                   user: User = Depends(get_current_user)):
    """Latest clean telemetry for a station."""
    from src.database import init_db, get_latest_clean_for_station
    conn = init_db()
    result = get_latest_clean_for_station(conn, station_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {station_id}")
    return result


@app.get("/api/pipeline/runs")
@limiter.limit("60/minute")
def pipeline_runs(request: Request, limit: int = Query(10, le=50),
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
# Telemetry endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/telemetry/raw")
@limiter.limit("60/minute")
def get_raw_telemetry(request: Request, limit: int = Query(200, le=500),
                      user: User = Depends(get_current_user)):
    """Recent raw telemetry readings."""
    from src.database import init_db
    from src.database._util import _rows_to_dicts
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM raw_telemetry ORDER BY ts DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


@app.get("/api/telemetry/clean")
@limiter.limit("60/minute")
def get_clean_telemetry(request: Request, limit: int = Query(200, le=500),
                        user: User = Depends(get_current_user)):
    """Recent clean (healed) telemetry readings."""
    from src.database import init_db
    from src.database._util import _rows_to_dicts
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


# ---------------------------------------------------------------------------
# Delivery & healing log endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/delivery/log")
@limiter.limit("60/minute")
def get_delivery_log(request: Request, limit: int = Query(100, le=500),
                     user: User = Depends(get_current_user)):
    """Recent delivery log entries."""
    from src.database import init_db
    from src.database._util import _rows_to_dicts
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


@app.get("/api/healing/log")
@limiter.limit("60/minute")
def get_healing_log(request: Request, limit: int = Query(100, le=500),
                    user: User = Depends(get_current_user)):
    """Recent healing log entries."""
    from src.database import init_db
    from src.database._util import _rows_to_dicts
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM healing_log ORDER BY created_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


@app.get("/api/healing/stats")
@limiter.limit("60/minute")
def get_healing_stats(request: Request, user: User = Depends(get_current_user)):
    """Healing assessment distribution, tool usage counts, and latest run info."""
    from src.database import init_db
    from src.database.healing import get_healing_stats as _get_healing_stats
    conn = init_db()
    return _get_healing_stats(conn)


# ---------------------------------------------------------------------------
# Pipeline & source stats (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/pipeline/stats")
@limiter.limit("60/minute")
def get_pipeline_stats(request: Request, user: User = Depends(get_current_user)):
    """Row counts from each major table for dashboard overview."""
    from src.database import init_db
    conn = init_db()
    tables = [
        "raw_telemetry", "clean_telemetry", "healing_log",
        "forecasts", "agricultural_alerts", "delivery_log",
        "pipeline_runs",
    ]
    counts = {}
    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = row[0] if row else 0
    return counts


@app.get("/api/sources")
@limiter.limit("60/minute")
def get_data_sources(request: Request, user: User = Depends(get_current_user)):
    """Data source distribution from raw_telemetry."""
    from src.database import init_db
    from src.database._util import _rows_to_dicts
    conn = init_db()
    rows = conn.execute(
        "SELECT source, COUNT(*) AS count FROM raw_telemetry GROUP BY source"
    ).fetchall()
    return _rows_to_dicts(conn, rows)


# ---------------------------------------------------------------------------
# Farmer / DPI endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/farmers")
@limiter.limit("60/minute")
def list_farmers(request: Request, user: User = Depends(get_current_user)):
    """List all simulated farmers."""
    try:
        from src.dpi.simulator import get_registry
        return get_registry().list_farmers()
    except Exception:
        return []


@app.get("/api/farmers/{phone}")
@limiter.limit("60/minute")
def get_farmer_detail(request: Request, phone: str, user: User = Depends(get_current_user)):
    """Get full DPI profile for a farmer by phone number."""
    from src.dpi.simulator import get_registry
    profile = get_registry().lookup_by_phone(phone)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No farmer with phone {phone}")
    # Serialize the dataclass to dict
    result: Dict[str, Any] = {
        "aadhaar": {
            "name": profile.aadhaar.name,
            "name_local": profile.aadhaar.name_local,
            "phone": profile.aadhaar.phone,
            "district": profile.aadhaar.district,
            "state": profile.aadhaar.state,
            "language": profile.aadhaar.language,
        },
        "primary_crops": profile.primary_crops,
        "total_area": profile.total_area,
        "land_records": [],
        "soil_health": None,
        "pmkisan": None,
        "pmfby": None,
        "kcc": None,
    }
    for lr in (profile.land_records or []):
        result["land_records"].append({
            "survey_number": lr.survey_number, "area_hectares": lr.area_hectares,
            "soil_type": lr.soil_type, "irrigation_type": lr.irrigation_type,
            "gps_lat": lr.gps_lat, "gps_lon": lr.gps_lon,
        })
    if profile.soil_health:
        sh = profile.soil_health
        result["soil_health"] = {
            "pH": sh.pH, "classification": sh.classification,
            "nitrogen_kg_ha": sh.nitrogen_kg_ha, "phosphorus_kg_ha": sh.phosphorus_kg_ha,
            "potassium_kg_ha": sh.potassium_kg_ha, "organic_carbon_pct": sh.organic_carbon_pct,
        }
    if profile.pmkisan:
        result["pmkisan"] = {
            "installments_received": profile.pmkisan.installments_received,
            "total_amount": profile.pmkisan.total_amount,
        }
    if profile.pmfby:
        result["pmfby"] = {
            "status": profile.pmfby.status, "sum_insured": profile.pmfby.sum_insured,
            "premium_paid": profile.pmfby.premium_paid,
        }
    if profile.kcc:
        result["kcc"] = {
            "credit_limit": profile.kcc.credit_limit, "outstanding": profile.kcc.outstanding,
            "repayment_status": profile.kcc.repayment_status,
        }
    return result


# ---------------------------------------------------------------------------
# Webhook (token-protected)
# ---------------------------------------------------------------------------

EVENTS_DIR = "events"
LOG_FILE = os.path.join(EVENTS_DIR, "webhook_log.jsonl")


@app.post("/webhook")
@limiter.limit("30/minute")
async def receive_webhook(request: Request, payload: dict):
    """Accept a JSON payload and append to event log."""
    if WEBHOOK_SECRET:
        token = request.headers.get("X-Webhook-Secret", "")
        if token != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    os.makedirs(EVENTS_DIR, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(payload) + "\n")
    return {"status": "received"}


@app.get("/webhook/history")
@limiter.limit("30/minute")
async def webhook_history(request: Request):
    """Return the last 20 webhook entries."""
    if not os.path.exists(LOG_FILE):
        return {"events": []}
    with open(LOG_FILE, "r") as f:
        last_lines = deque(f, maxlen=20)
    return {"events": [json.loads(ln.strip()) for ln in last_lines if ln.strip()]}
