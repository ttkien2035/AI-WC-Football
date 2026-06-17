# World Cup 2026 Predictor — backend (FastAPI + ML ensemble)
FROM python:3.12-slim

# libgomp1: OpenMP runtime required by xgboost
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt

# app code + ML pipeline (nightly auto-retrain runs in-container)
COPY app ./app
COPY ml ./ml

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

# 4 workers: serve concurrent users in parallel (a 20k-sim predict in one worker
# no longer blocks others). The scheduler self-elects to ONE worker via a file
# lock; the SQLite cache is WAL-mode + shared on the /data volume.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
