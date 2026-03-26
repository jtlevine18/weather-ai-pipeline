FROM python:3.11-slim

WORKDIR /app

# System deps for libgomp (XGBoost) + curl (health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Health endpoint for GitHub Actions polling
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Run pipeline on startup, then serve a simple health endpoint
CMD ["python", "entrypoint.py"]
