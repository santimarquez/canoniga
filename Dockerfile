FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples
COPY benchmarks ./benchmarks
COPY config ./config

RUN python -m pip install --upgrade pip \
    && pip install -e .

EXPOSE 8000

CMD ["python", "-m", "als_intel.webui"]
