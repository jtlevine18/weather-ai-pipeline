FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    ca-certificates \
    curl \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt

# Copy project
COPY . .

ENV STREAMLIT_HOME=/tmp/.streamlit
RUN mkdir -p /tmp/.streamlit

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# nginx proxies port 7860 → FastAPI (8000) + Streamlit (8501)
CMD ["sh", "-c", "nginx && uvicorn src.api:app --host 0.0.0.0 --port 8000 & streamlit run streamlit_app/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true & wait"]
