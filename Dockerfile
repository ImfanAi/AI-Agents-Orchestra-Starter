# ===== 1) Build stage (optional: cache usage) =====
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Copy requirements
COPY requirements.txt /app/requirements.txt

# Install packages
RUN pip install --upgrade pip \
 && pip install -r /app/requirements.txt

# Copy the source
COPY . /app

# non-root users (security)
RUN useradd -u 10001 -m appuser
USER appuser

# Network port
EXPOSE 8000

# Health Check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD \
  curl -fsS http://127.0.0.1:8000/health || exit 1

# Run (FastAPI)
ENV PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
