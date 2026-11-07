FROM python:3.11.17-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY db ./db
COPY monitor ./monitor
COPY migrations ./migrations
COPY alembic.ini ./

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -e ".[dev]"

RUN mkdir -p /data \
    && chown -R nobody:nogroup /app /data

USER nobody

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]