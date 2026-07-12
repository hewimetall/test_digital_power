# Test Digital Power API

Small FastAPI service that issues JWT tokens and proxies avatar images from a
DNMonster service, caching fetched images in Redis.

## Requirements

- Python 3.10 or newer
- Poetry
- Redis for the avatar cache
- DNMonster-compatible avatar service
- Docker and Docker Compose, if running the full local stack

## Setup

Install dependencies with Poetry:

```bash
poetry install
```

## Environment

The application reads these optional environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `AUTH_SECRET` | `no_sec` | Secret used to sign JWT access and refresh tokens. |
| `REDIS_HOST` | `redis` | Redis hostname used by the avatar cache. |
| `DNMONSTER_URL` | `http://dnmonster:8080` | Base URL for avatar image generation. |

For local runs outside Docker Compose, set `REDIS_HOST=localhost` and point
`DNMONSTER_URL` at a reachable DNMonster service.

## Run

Run the API directly:

```bash
AUTH_SECRET=change-me REDIS_HOST=localhost poetry run uvicorn app.main:app --reload
```

Run the full stack with Redis, DNMonster, and nginx:

```bash
docker compose up --build
```

The compose stack exposes nginx on port 80.

## Test

Run the test suite:

```bash
poetry run pytest
```

Run tests with the coverage gate:

```bash
poetry run pytest --cov=app --cov-report=term-missing --cov-fail-under=93
```

## Dependency audit

Audit the installed Python environment with:

```bash
poetry run pip-audit
```
