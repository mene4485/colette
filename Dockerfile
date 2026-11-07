# Backend Colette en ligne (voix + agent H cloud) — Railway / Render.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 COLETTE_SITE=demo
WORKDIR /app
COPY requirements-backend.txt .
RUN pip install -r requirements-backend.txt
COPY colette ./colette
CMD ["sh", "-c", "uvicorn colette.hosted:app --host 0.0.0.0 --port ${PORT:-8080} --ws-ping-interval 20"]
