# Construction OS

Production-oriented modular monolith for managing construction projects.

## Stack

- Python 3.12, FastAPI, Pydantic
- SQLAlchemy 2, Alembic, PostgreSQL
- Redis
- Docker Compose
- pytest, Ruff, mypy

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

API health check: `GET http://localhost:8000/api/v1/health`

## Architecture

`Project` is the aggregate anchor. Project-owned records carry `project_id`, while
`company_id` is the tenant boundary. Business modules live under `app/modules`;
shared infrastructure lives under `app/core` and `app/db`.

The first milestone intentionally contains only platform foundations and core domain
entities. Engineering calculations will be deterministic, versioned Python tools;
LLMs will only orchestrate and explain them.
