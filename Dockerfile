FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# API space uses requirements-dashboard.txt (lightweight)
# Pipeline space uses full requirements.txt (set SPACE_MODE=pipeline in HF env vars)
COPY requirements-dashboard.txt requirements.txt ./
ARG SPACE_MODE=api
RUN if [ "$SPACE_MODE" = "pipeline" ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements-dashboard.txt; \
    fi

# Copy project
COPY . .

ENV STREAMLIT_HOME=/tmp/.streamlit
RUN mkdir -p /tmp/.streamlit

# Run as non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app /tmp/.streamlit
USER appuser

EXPOSE 7860

# Health check — both modes serve /health on 7860
HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=30s \
    CMD curl -f http://localhost:7860/health || exit 1

# SPACE_MODE env var determines what to run:
#   "api" (default) — FastAPI on 7860
#   "pipeline" — Run pipeline, serve status page on 7860
ENV SPACE_MODE=api
CMD ["sh", "-c", "if [ \"$SPACE_MODE\" = 'pipeline' ]; then python pipeline-runner/entrypoint.py; else uvicorn src.api:app --host 0.0.0.0 --port 7860; fi"]
