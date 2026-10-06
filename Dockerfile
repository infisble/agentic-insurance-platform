FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
RUN pip install ".[redis]"

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 app && mkdir -p /data/documents && chown -R app /data
USER app

EXPOSE 8000
# Migrations run before the API starts; in a cluster they move to a release job (ADR 0009).
CMD ["sh", "-c", "alembic upgrade head && uvicorn aip.api.app:app --host 0.0.0.0 --port 8000"]
