"""Pipeline runner entrypoint for HF Spaces GPU Space.

On startup: runs the full pipeline, then serves a health endpoint
so GitHub Actions can poll for completion.
"""
import asyncio
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add parent dir to path so src/ imports work
sys.path.insert(0, os.path.dirname(__file__))

STATUS = {"state": "starting", "started_at": None, "finished_at": None, "result": None}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(STATUS, default=str).encode())

    def log_message(self, format, *args):
        pass  # suppress request logs


def serve_health():
    server = HTTPServer(("0.0.0.0", 7860), HealthHandler)
    server.serve_forever()


def run_pipeline():
    global STATUS
    STATUS["state"] = "running"
    STATUS["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        from config import get_config
        from src.pipeline import WeatherPipeline

        config = get_config()
        pipeline = WeatherPipeline(config)
        result = asyncio.run(pipeline.run())

        STATUS["state"] = "complete"
        STATUS["result"] = result
    except Exception as exc:
        STATUS["state"] = "failed"
        STATUS["result"] = str(exc)
    finally:
        STATUS["finished_at"] = datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    # Start health server in background
    health_thread = threading.Thread(target=serve_health, daemon=True)
    health_thread.start()

    # Run pipeline
    run_pipeline()

    # Keep alive so HF Spaces doesn't restart (it'll auto-sleep after idle timeout)
    print(f"Pipeline {STATUS['state']}. Waiting for auto-sleep...")
    health_thread.join()
