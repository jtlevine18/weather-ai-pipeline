"""Unified REST API for the weather pipeline.

Consolidates health, webhook, and data endpoints into a single FastAPI app.
Run with: python run_api.py (or: uvicorn src.api:app --reload)
"""

from __future__ import annotations
import json
import logging
import os
import uuid
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, Depends, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from prometheus_fastapi_instrumentator import Instrumentator

from src.auth import get_current_user, require_operator, User, create_token, verify_password, hash_password
from src.health import get_health_status

log = logging.getLogger(__name__)

# Schema is initialized on startup via the FastAPI lifespan hook, not at
# import time. This keeps `import src.api` working even if DATABASE_URL is
# not configured (e.g. during test collection).
from src.database import init_db as _init_db


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        _init_db()
    except Exception as exc:
        log.exception("Database initialization failed on startup: %s", exc)
    yield

def _get_conn():
    """Get a pooled DB connection without running DDL."""
    from src.database._util import PgConnection, get_database_url
    return PgConnection(get_database_url())

app = FastAPI(
    title="Weather Pipeline API",
    version="1.0.0",
    description="REST API for the Kerala/Tamil Nadu agricultural weather pipeline",
    lifespan=_lifespan,
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS — configurable via ALLOWED_ORIGINS env var (comma-separated)
# ---------------------------------------------------------------------------

_DEFAULT_ALLOWED_ORIGINS = [
    "https://jtlevine-ai-weather-pipeline-runner.hf.space",
    "https://weather-forecast.jeff-levine.com",
    "https://weather-ai-pipeline.vercel.app",
]
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if _allowed_origins_env:
    _allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
else:
    _allowed_origins = _DEFAULT_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Webhook-Secret"],
)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

Instrumentator().instrument(app).expose(app)

# ---------------------------------------------------------------------------
# Webhook secret
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
if not WEBHOOK_SECRET:
    log.warning(
        "WEBHOOK_SECRET not set — webhook endpoints will accept unauthenticated requests. "
        "Set WEBHOOK_SECRET in production."
    )


# ---------------------------------------------------------------------------
# Pipeline tracker state (used by root page, /api/pipeline/status, and
# the /api/pipeline/trigger endpoint defined further down)
# ---------------------------------------------------------------------------

_PIPELINE_STEPS = [
    ("step_ingest", "Collecting station data"),
    ("step_heal", "Fixing data issues"),
    ("step_forecast", "Generating forecasts"),
    ("step_downscale", "Localizing to farmer GPS"),
    ("step_translate", "Writing advisories"),
    ("step_deliver", "Sending SMS"),
]

_pipeline_status: Dict[str, Any] = {
    "running": False,
    "current_step": None,
    "current_step_index": 0,
    "total_steps": len(_PIPELINE_STEPS),
    "last_result": None,
    "last_run": None,
}


# ---------------------------------------------------------------------------
# Health + root tracker page (public)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def root():
    """Pipeline tracker for the HF Space. Shows current run state and a Run button."""
    ps = _pipeline_status
    running = ps["running"]
    current_idx = ps.get("current_step_index", 0)
    last = ps.get("last_result")

    rows = ""
    for idx, (_method, label) in enumerate(_PIPELINE_STEPS, start=1):
        if running:
            if idx < current_idx:
                cls = "done"
            elif idx == current_idx:
                cls = "active"
            else:
                cls = "pending"
        elif last and last.get("status") in ("ok", "partial"):
            cls = "done"
        else:
            cls = "pending"
        rows += f'<div class="step-row"><div class="step-dot {cls}"></div><span class="step-name">{label}</span></div>\n'

    last_html = ""
    if last and not running:
        status = last.get("status", "unknown")
        dur = last.get("duration_s", 0) or 0
        cls = "ok" if status in ("ok", "partial") else "failed"
        last_html = f'<div class="last-run"><span class="{cls}">{status.upper()}</span> — {dur:.0f}s</div>'

    btn_disabled = "disabled" if running else ""
    btn_text = "Running..." if running else "Run Pipeline"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>Weather AI</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #faf8f5; color: #1a1a1a; padding: 32px; max-width: 480px; margin: 0 auto; }}
  h1 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; }}
  .subtitle {{ color: #888; font-size: 0.85rem; margin-bottom: 24px; }}
  .link {{ color: #2d5b7d; text-decoration: none; font-weight: 600; }}
  .link:hover {{ text-decoration: underline; }}
  .pipeline-tracker {{ background: #fff; border: 1px solid #e0dcd5; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
  .pipeline-tracker h3 {{ font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #2d5b7d; margin-bottom: 12px; }}
  .step-row {{ display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: 0.82rem; }}
  .step-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .step-dot.done {{ background: #2a9d8f; }}
  .step-dot.active {{ background: #2d5b7d; animation: pulse 1.2s infinite; }}
  .step-dot.pending {{ background: #e0dcd5; }}
  .step-dot.failed {{ background: #e63946; }}
  .step-name {{ font-weight: 600; }}
  .trigger-btn {{ display: inline-block; margin-top: 12px; padding: 8px 20px; background: #2d5b7d; color: #fff; border: none; border-radius: 6px; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; cursor: pointer; }}
  .trigger-btn:hover {{ background: #244862; }}
  .trigger-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .last-run {{ font-size: 0.78rem; color: #888; margin-top: 8px; }}
  .last-run .ok {{ color: #2a9d8f; font-weight: 600; }}
  .last-run .failed {{ color: #e63946; font-weight: 600; }}
  @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
</style>
</head>
<body>
  <h1>Weather AI</h1>
  <p class="subtitle"><a class="link" href="https://weather-forecast.jeff-levine.com" target="_blank">Open Dashboard</a></p>

  <div class="pipeline-tracker">
    <h3>Pipeline</h3>
    {rows}
    <button class="trigger-btn" {btn_disabled} onclick="fetch('/api/pipeline/trigger',{{method:'POST'}}).then(()=>location.reload())">{btn_text}</button>
    {last_html}
  </div>
</body>
</html>"""


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
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash, role FROM users WHERE username = %s",
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
    with _get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            raise HTTPException(status_code=409, detail="Users already exist — use /auth/token")
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (%s,%s,%s,%s)",
            [str(uuid.uuid4()), username, hash_password(password), "operator"],
        )
        token = create_token(username, "operator")
        return {"access_token": token, "token_type": "bearer", "role": "operator"}


@app.post("/auth/register", status_code=201)
@limiter.limit("5/minute")
def register(request: Request, username: str, password: str, role: str = "viewer",
             operator: User = Depends(require_operator)):
    """Create a new user (operator-only)."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (%s,%s,%s,%s)",
            [str(uuid.uuid4()), username, hash_password(password), role],
        )
        return {"username": username, "role": role}


# ---------------------------------------------------------------------------
# Data endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/stations")
@limiter.limit("60/minute")
def list_stations(request: Request, ):
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
                  ):
    """Recent forecasts across all stations. Optional forecast_day filter (0-6)."""
    from src.database import get_recent_forecasts
    with _get_conn() as conn:
        results = get_recent_forecasts(conn, limit=limit)
        if forecast_day is not None:
            results = [r for r in results if r.get("forecast_day", 0) == forecast_day]
        return results


@app.get("/api/alerts")
@limiter.limit("60/minute")
def get_alerts(request: Request, limit: int = Query(50, le=200),
               ):
    """Recent agricultural alerts / advisories."""
    from src.database import get_recent_alerts
    with _get_conn() as conn:
        return get_recent_alerts(conn, limit=limit)


@app.get("/api/station/{station_id}/latest")
@limiter.limit("60/minute")
def station_latest(request: Request, station_id: str,
                   ):
    """Latest clean telemetry for a station."""
    from src.database import get_latest_clean_for_station
    with _get_conn() as conn:
        result = get_latest_clean_for_station(conn, station_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No data for {station_id}")
        return result


@app.get("/api/pipeline/runs")
@limiter.limit("60/minute")
def pipeline_runs(request: Request, limit: int = Query(10, le=50),
                  ):
    """Recent pipeline run history."""
    from src.database._util import _rows_to_dicts
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT %s", [limit]
        ).fetchall()
        return _rows_to_dicts(conn, rows)


# ---------------------------------------------------------------------------
# Telemetry endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/telemetry/raw")
@limiter.limit("60/minute")
def get_raw_telemetry(request: Request, limit: int = Query(200, le=500),
                      ):
    """Recent raw telemetry readings."""
    from src.database._util import _rows_to_dicts
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM raw_telemetry ORDER BY ts DESC LIMIT %s", [limit]
        ).fetchall()
        return _rows_to_dicts(conn, rows)


@app.get("/api/telemetry/clean")
@limiter.limit("60/minute")
def get_clean_telemetry(request: Request, limit: int = Query(200, le=500),
                        ):
    """Recent clean (healed) telemetry readings."""
    from src.database._util import _rows_to_dicts
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT %s", [limit]
        ).fetchall()
        return _rows_to_dicts(conn, rows)


# ---------------------------------------------------------------------------
# Delivery & healing log endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/delivery/log")
@limiter.limit("60/minute")
def get_delivery_log(request: Request, limit: int = Query(100, le=500),
                     ):
    """Recent delivery log entries."""
    from src.database._util import _rows_to_dicts
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT %s", [limit]
        ).fetchall()
        return _rows_to_dicts(conn, rows)


@app.get("/api/healing/log")
@limiter.limit("60/minute")
def get_healing_log(request: Request, limit: int = Query(100, le=500),
                    ):
    """Recent healing log entries."""
    from src.database._util import _rows_to_dicts
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM healing_log ORDER BY created_at DESC LIMIT %s", [limit]
        ).fetchall()
        return _rows_to_dicts(conn, rows)


@app.get("/api/healing/stats")
@limiter.limit("60/minute")
def get_healing_stats(request: Request, ):
    """Healing assessment distribution, tool usage counts, and latest run info."""
    from src.database.healing import get_healing_stats as _get_healing_stats
    with _get_conn() as conn:
        return _get_healing_stats(conn)


# ---------------------------------------------------------------------------
# Pipeline & source stats (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/pipeline/stats")
@limiter.limit("60/minute")
def get_pipeline_stats(request: Request, ):
    """Row counts from each major table for dashboard overview."""
    with _get_conn() as conn:
        tables = [
            "raw_telemetry", "clean_telemetry", "healing_log",
            "forecasts", "agricultural_alerts", "delivery_log",
            "pipeline_runs",
        ]
        from src.database.safe_sql import safe_table
        counts = {}
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) FROM {safe_table(table)}").fetchone()
            counts[table] = row[0] if row else 0
        return counts


@app.get("/api/sources")
@limiter.limit("60/minute")
def get_data_sources(request: Request, ):
    """Data source distribution from raw_telemetry."""
    from src.database._util import _rows_to_dicts
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT source, COUNT(*) AS count FROM raw_telemetry GROUP BY source"
        ).fetchall()
        return _rows_to_dicts(conn, rows)


# ---------------------------------------------------------------------------
# Farmer / DPI endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/farmers")
@limiter.limit("60/minute")
def list_farmers(request: Request, ):
    """List all simulated farmers."""
    try:
        from src.dpi.simulator import get_registry
        return get_registry().list_farmers()
    except Exception:
        return []


@app.get("/api/farmers/{phone}")
@limiter.limit("60/minute")
def get_farmer_detail(request: Request, phone: str, ):
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
# Eval results (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/evals")
@limiter.limit("60/minute")
def get_eval_results(request: Request, ):
    """Load eval results from JSON files in tests/eval_results/."""
    results_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "eval_results")
    results = {}
    for name in ("healing", "forecast", "rag", "advisory", "translation", "dpi", "conversation"):
        path = os.path.join(results_dir, name + ".json")
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    results[name] = json.load(fh)
            except Exception:
                pass
    return results


# ---------------------------------------------------------------------------
# Conversation log (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/conversation/log")
@limiter.limit("60/minute")
def get_conversation_log(request: Request, limit: int = Query(50, le=500),
                         ):
    """Recent conversation log entries."""
    try:
        from src.database._util import _rows_to_dicts
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_log ORDER BY created_at DESC LIMIT %s", [limit]
            ).fetchall()
            return _rows_to_dicts(conn, rows)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Delivery metrics (authenticated)
# ---------------------------------------------------------------------------

@app.get("/api/delivery/metrics")
@limiter.limit("60/minute")
def get_delivery_metrics(request: Request, limit: int = Query(200, le=500),
                         ):
    """Delivery metrics per station per run."""
    try:
        from src.database._util import _rows_to_dicts
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_metrics ORDER BY created_at DESC LIMIT %s", [limit]
            ).fetchall()
            return _rows_to_dicts(conn, rows)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Chat (authenticated)
# ---------------------------------------------------------------------------

@app.post("/api/chat")
@limiter.limit("20/minute")
def chat_message(request: Request, payload: dict,
                 ):
    """Send a chat message and get a response from Claude."""
    message = payload.get("message", "")
    history = payload.get("history", [])
    farmer_phone = payload.get("farmer_phone")

    try:
        import anthropic
        client = anthropic.Anthropic()

        system = (
            "You are a Weather AI assistant for Kerala and Tamil Nadu farmers. "
            "You help with weather forecasts, agricultural advisories, pipeline status, "
            "and station data. Be concise and actionable."
        )

        if farmer_phone:
            try:
                from src.dpi.simulator import get_registry
                profile = get_registry().lookup_by_phone(farmer_phone)
                if profile:
                    system += (
                        f"\n\nCurrent farmer: {profile.aadhaar.name}, "
                        f"District: {profile.aadhaar.district}, "
                        f"State: {profile.aadhaar.state}, "
                        f"Crops: {', '.join(profile.primary_crops)}, "
                        f"Area: {profile.total_area:.2f} ha"
                    )
            except Exception:
                pass

        messages = []
        for h in history[-10:]:
            if h.get("role") in ("user", "assistant"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=system,
            messages=messages,
        )
        return {"response": resp.content[0].text}
    except ImportError:
        return {"response": "Chat requires the anthropic package."}
    except Exception as exc:
        logging.getLogger(__name__).exception("Chat endpoint error")
        return {"response": "Sorry, I couldn't process that request. Please try again."}


# ---------------------------------------------------------------------------
# Mini demo (public — no auth, no API keys)
# ---------------------------------------------------------------------------

@app.post("/api/demo/run")
@limiter.limit("5/minute")
async def run_mini_demo(request: Request):
    """Run a mini demo: synthetic ingest + rule-based heal. No API keys needed."""
    from config import STATIONS, FaultInjectionConfig
    from src.ingestion import generate_synthetic_reading
    from src.healing import RuleBasedFallback

    fault_config = FaultInjectionConfig(
        typo_rate=0.25, offline_rate=0.25, drift_rate=0.25, missing_rate=0.25,
    )
    healer = RuleBasedFallback()
    results = []
    for station in STATIONS[:3]:
        reading = generate_synthetic_reading(station, fault_config)
        healed = healer.heal(reading)
        results.append({
            "raw": reading,
            "healed": healed,
            "station": station.name,
            "fault_injected": reading.get("fault_type"),
        })

    return {"demo": True, "stations_used": 3, "results": results}


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


def _install_progress_tracking(pipeline):
    """Wrap pipeline step methods so _pipeline_status updates as each step starts."""
    for idx, (method_name, _label) in enumerate(_PIPELINE_STEPS, start=1):
        original = getattr(pipeline, method_name, None)
        if original is None:
            continue

        def make_wrapper(orig, num, name):
            async def wrapper(*args, **kwargs):
                _pipeline_status["current_step"] = name
                _pipeline_status["current_step_index"] = num
                return await orig(*args, **kwargs)
            return wrapper

        setattr(pipeline, method_name, make_wrapper(original, idx, method_name))


@app.post("/api/pipeline/trigger")
@limiter.limit("6/minute")
async def trigger_pipeline(request: Request):
    """Trigger a full pipeline run in a background thread. Idempotent while running."""
    if _pipeline_status["running"]:
        return {"status": "already_running", "message": "A pipeline run is already in progress"}

    import threading
    import time as _time
    from datetime import datetime as _dt

    def _run():
        import asyncio
        _pipeline_status["running"] = True
        _pipeline_status["current_step"] = None
        _pipeline_status["current_step_index"] = 0
        _pipeline_status["last_result"] = None
        start = _time.time()
        try:
            from config import get_config
            from src.pipeline import WeatherPipeline
            cfg = get_config()
            pipeline = WeatherPipeline(cfg)
            _install_progress_tracking(pipeline)
            asyncio.run(pipeline.run())
            _pipeline_status["last_result"] = {
                "status": "ok",
                "duration_s": round(_time.time() - start, 1),
            }
        except Exception as exc:
            logging.getLogger(__name__).exception("Triggered pipeline failed")
            _pipeline_status["last_result"] = {
                "status": "failed",
                "error": str(exc)[:500],
                "duration_s": round(_time.time() - start, 1),
            }
        finally:
            _pipeline_status["last_run"] = _dt.utcnow().isoformat()
            _pipeline_status["running"] = False
            _pipeline_status["current_step"] = None
            _pipeline_status["current_step_index"] = 0

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"status": "started"}


@app.get("/api/pipeline/status")
def pipeline_status_endpoint():
    """Current in-memory pipeline run state. Used by the tracker page and weekly GHA."""
    return _pipeline_status


@app.get("/api/pipeline/mos-status")
@limiter.limit("60/minute")
def mos_status(request: Request):
    """Check MOS model training status and metrics."""
    model_path = os.path.join("models", "hybrid_mos.json")
    metrics_path = os.path.join("metrics", "mos_metrics.json")
    trained = os.path.exists(model_path)
    metrics = None
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path) as f:
                metrics = json.load(f)
        except Exception:
            pass
    return {"trained": trained, "metrics": metrics}


@app.post("/api/pipeline/retrain-mos")
@limiter.limit("2/minute")
async def retrain_mos(request: Request):
    """Trigger MOS model retraining (export training data + train XGBoost) in background."""
    import threading
    import subprocess
    import sys as _sys

    def _retrain():
        try:
            subprocess.run(
                [_sys.executable, "scripts/export_training_data.py"],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [_sys.executable, "scripts/train_mos.py"],
                check=True, capture_output=True, text=True,
            )
            logging.getLogger(__name__).info("MOS model retrained successfully")
        except subprocess.CalledProcessError as exc:
            logging.getLogger(__name__).error(
                "MOS retrain failed: %s", (exc.stderr or exc.stdout or str(exc))[:500]
            )

    thread = threading.Thread(target=_retrain, daemon=True)
    thread.start()
    return {"status": "triggered"}


@app.post("/api/pipeline/run-evals")
@limiter.limit("2/minute")
async def run_evals(request: Request):
    """Trigger all 7 eval scripts in a background thread. Results saved to tests/eval_results/."""
    import threading
    import subprocess
    import sys as _sys

    eval_scripts = [
        "tests/eval_healing.py",
        "tests/eval_forecast.py",
        "tests/eval_rag.py",
        "tests/eval_advisory.py",
        "tests/eval_translation.py",
        "tests/eval_dpi.py",
        "tests/eval_conversation.py",
    ]

    def _run_evals():
        log = logging.getLogger(__name__)
        for script in eval_scripts:
            try:
                subprocess.run(
                    [_sys.executable, script],
                    check=True, capture_output=True, text=True, timeout=120,
                )
                log.info("Eval passed: %s", script)
            except subprocess.CalledProcessError as exc:
                log.warning("Eval failed: %s — %s", script, (exc.stderr or exc.stdout or str(exc))[:300])
            except subprocess.TimeoutExpired:
                log.warning("Eval timed out: %s", script)

    thread = threading.Thread(target=_run_evals, daemon=True)
    thread.start()
    return {"status": "triggered", "scripts": len(eval_scripts)}


@app.get("/webhook/history")
@limiter.limit("30/minute")
async def webhook_history(request: Request):
    """Return the last 20 webhook entries."""
    if not os.path.exists(LOG_FILE):
        return {"events": []}
    with open(LOG_FILE, "r") as f:
        last_lines = deque(f, maxlen=20)
    return {"events": [json.loads(ln.strip()) for ln in last_lines if ln.strip()]}


# ---------------------------------------------------------------------------
# Historical forecast endpoint for LastMileBench counterfactual evaluation
# ---------------------------------------------------------------------------

@app.post("/api/forecast_historical")
@limiter.limit("10/minute")
async def forecast_historical(request: Request):
    """Run NeuralGCM on a historical date for a specific lat/lon.

    Used by the LastMileBench weather adapter to test the actual model
    on historical monsoon anomaly years (2002, 2009, 2014, 2019, etc.).

    Body: {"date": "2019-06-18", "lat": 26.24, "lon": 73.02}
    Returns: {"forecast": [...], "model": "neuralgcm", "init_time": "..."}
    """
    from config import StationConfig

    body = await request.json()
    target_date = body.get("date")
    lat = body.get("lat")
    lon = body.get("lon")
    if not all([target_date, lat, lon]):
        return {"error": "date, lat, lon required"}, 400

    # Create a temporary station at the requested location
    temp_station = StationConfig(
        station_id=f"bench-{lat:.2f}-{lon:.2f}",
        name=f"Benchmark ({lat}, {lon})",
        lat=float(lat),
        lon=float(lon),
        altitude_m=100.0,
        state="benchmark",
        crop_context="rice",
        language="en",
    )

    try:
        from src.neuralgcm_client import NeuralGCMClient
        client = NeuralGCMClient(forecast_hours=168)
        forecasts, meta = await client.get_forecasts_batch(
            [temp_station], target_date=target_date
        )
        station_forecast = forecasts.get(temp_station.station_id, [])
        return {
            "forecast": station_forecast,
            "model": "neuralgcm",
            "init_time": meta.init_time,
            "inference_time_s": meta.inference_time_s,
        }
    except Exception as e:
        # Fall back to Open-Meteo archive if NeuralGCM unavailable
        from src.weather_clients import OpenMeteoClient
        client = OpenMeteoClient()
        try:
            forecast = client.get_forecast(float(lat), float(lon), days=7)
            return {
                "forecast": forecast,
                "model": "open_meteo_fallback",
                "error_detail": str(e),
            }
        except Exception as e2:
            return {"error": f"NeuralGCM: {e}, Open-Meteo: {e2}"}, 500
