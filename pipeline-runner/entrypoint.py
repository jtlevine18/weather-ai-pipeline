"""Pipeline runner entrypoint for HF Spaces GPU Space.

On startup: runs the full pipeline, serves a status page showing
current step progress.
"""
import asyncio
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))

STATUS = {
    "state": "starting",
    "step": 0,
    "step_name": "Initializing",
    "started_at": None,
    "finished_at": None,
    "steps_completed": [],
    "error": None,
}

STEPS = [
    "1. Ingest — Scraping IMD weather data",
    "2. Heal — AI agent cleaning anomalies",
    "3. Forecast — NeuralGCM + XGBoost predictions",
    "4. Downscale — NASA satellite → farmer GPS",
    "5. Translate — RAG + Claude bilingual advisories",
    "6. Deliver — Sending SMS advisories",
]

CSS = """
body { font-family: 'DM Sans', sans-serif; background: #faf8f5; color: #1a1a1a; margin: 0; padding: 40px; }
.container { max-width: 600px; margin: 0 auto; }
h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; }
.subtitle { color: #999; font-size: 0.85rem; margin-bottom: 24px; }
.status { font-size: 1.1rem; font-weight: 600; margin-bottom: 20px; }
.status.running { color: #1976D2; }
.status.complete { color: #2a9d8f; }
.status.failed { color: #e63946; }
.status.starting { color: #f4a261; }
.status.paused { color: #999; }
.steps { list-style: none; padding: 0; }
.steps li { padding: 10px 14px; margin: 4px 0; border-radius: 8px; font-size: 0.85rem; border: 1px solid #e0dcd5; background: #fff; }
.steps li.done { border-left: 3px solid #2a9d8f; color: #1a1a1a; }
.steps li.active { border-left: 3px solid #1976D2; color: #1976D2; font-weight: 600; background: #f0f7ff; }
.steps li.pending { color: #bbb; }
.meta { margin-top: 20px; font-size: 0.75rem; color: #999; }
""".strip()


def render_html():
    state = STATUS["state"]
    current_step = STATUS["step"]

    state_labels = {
        "starting": "Initializing...",
        "running": f"Running — Step {current_step}/6",
        "complete": "Pipeline Complete",
        "failed": "Pipeline Failed",
        "paused": "Paused (waiting for next scheduled run)",
    }

    steps_html = ""
    for i, label in enumerate(STEPS):
        step_num = i + 1
        if step_num < current_step:
            steps_html += f'<li class="done">{label}</li>'
        elif step_num == current_step:
            steps_html += f'<li class="active">{label}</li>'
        else:
            steps_html += f'<li class="pending">{label}</li>'

    meta_parts = []
    if STATUS["started_at"]:
        meta_parts.append(f"Started: {STATUS['started_at'][:19]}Z")
    if STATUS["finished_at"]:
        meta_parts.append(f"Finished: {STATUS['finished_at'][:19]}Z")
    if STATUS["error"]:
        meta_parts.append(f"Error: {str(STATUS['error'])[:200]}")

    state_class = state
    state_label = state_labels.get(state, state)
    meta = " | ".join(meta_parts) if meta_parts else ""

    return f"""<!DOCTYPE html>
<html>
<head>
  <title>Pipeline Runner</title>
  <meta http-equiv="refresh" content="5">
  <style>{CSS}</style>
</head>
<body>
  <div class="container">
    <h1>Pipeline Runner</h1>
    <p class="subtitle">AI Weather Pipeline — GPU Space</p>
    <div class="status {state_class}">{state_label}</div>
    <ul class="steps">{steps_html}</ul>
    <div class="meta">
      {meta}
      <br>Auto-refreshes every 5 seconds.
    </div>
  </div>
</body>
</html>"""


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(STATUS, default=str).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(render_html().encode())

    def log_message(self, format, *args):
        pass


def serve():
    HTTPServer(("0.0.0.0", 7860), StatusHandler).serve_forever()


def run_pipeline():
    global STATUS
    STATUS["state"] = "running"
    STATUS["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        from config import get_config
        from src.pipeline import WeatherPipeline

        config = get_config()
        pipeline = WeatherPipeline(config)

        # Monkey-patch step methods to update STATUS
        original_steps = {}
        step_names = {
            "step_ingest": 1, "step_heal": 2, "step_forecast": 3,
            "step_downscale": 4, "step_translate": 5, "step_deliver": 6,
        }
        for method_name, step_num in step_names.items():
            original = getattr(pipeline, method_name)
            original_steps[method_name] = original

            def make_wrapper(orig, num, name):
                async def wrapper(*args, **kwargs):
                    STATUS["step"] = num
                    STATUS["step_name"] = STEPS[num - 1]
                    result = await orig(*args, **kwargs)
                    STATUS["steps_completed"].append(num)
                    return result
                return wrapper

            setattr(pipeline, method_name, make_wrapper(original, step_num, method_name))

        result = asyncio.run(pipeline.run())
        STATUS["state"] = "complete"
        STATUS["step"] = 7
    except Exception as exc:
        STATUS["state"] = "failed"
        STATUS["error"] = str(exc)
    finally:
        STATUS["finished_at"] = datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    run_pipeline()
    print(f"Pipeline {STATUS['state']}. Waiting for auto-sleep...")
    t.join()
