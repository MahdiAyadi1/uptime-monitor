FROM python:3.11.17-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

COPY pyproject.toml README.md ./
COPY --chown=app:app app ./app
COPY --chown=app:app db ./db
COPY --chown=app:app monitor ./monitor
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini .

RUN pip install .

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]