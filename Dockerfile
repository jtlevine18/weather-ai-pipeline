FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

ENV STREAMLIT_HOME=/tmp/.streamlit
RUN mkdir -p /tmp/.streamlit

EXPOSE 8000 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use exec form + tini-like approach for signal handling
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port 8000 & streamlit run streamlit_app/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true & wait"]
