# Build stage: compile Vue frontend
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
COPY src/als_intel/i18n/locales /src/als_intel/i18n/locales
RUN node scripts/sync-locales.mjs && npm run build

# Runtime stage: Python API + static SPA
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY assets ./assets
COPY examples ./examples
COPY benchmarks ./benchmarks
COPY config ./config

COPY --from=frontend-build /assets/dist ./assets/dist

RUN python -m pip install --upgrade pip \
    && pip install -e .

EXPOSE 8000

CMD ["python", "-m", "als_intel.webui"]
