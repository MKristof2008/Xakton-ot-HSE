# Dockerfile — сборка «Проверено» в один образ.
# Многоэтапная: фронт собирается Node, потом кладётся в статику FastAPI.

FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pillow требует libjpeg/zlib; ставим минимальный набор
RUN apt-get update \
 && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY ml/ ./ml/
COPY backend/ ./backend/
COPY --from=web /web/dist ./frontend/dist

# данные (SQLite) живут в томе
ENV VERDICT_DB=/data/verdict.db
RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
