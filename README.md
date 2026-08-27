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

Apply the database schema and start the API:

```bash
docker compose run --rm api alembic upgrade head
docker compose up
```

Authentication starts with `POST /api/v1/auth/register`. It atomically creates a
company and its owner. Use the returned bearer token for the project endpoints.

## Implemented API

- `POST /api/v1/auth/register`, `POST /api/v1/auth/token`, `GET /api/v1/auth/me`
- `POST /api/v1/projects`, `GET /api/v1/projects`, `GET /api/v1/projects/{project_id}`
- list, add, change, and remove project members under
  `/api/v1/projects/{project_id}/members`
- create, list, read, update, and delete construction structures under
  `/api/v1/projects/{project_id}/structures`

Project access always requires both a matching `company_id` and a `ProjectMember`
record. Owners and administrators manage members. Owners, administrators, project
managers, and engineers manage structures; all project roles can read them. Owner
changes are owner-only, and the last project owner cannot be removed or downgraded.

## Server staging deployment

Staging uses `compose.staging.yaml` and stores generated secrets only in
`/opt/construction-os/.env` on the server. The `Deploy staging` GitHub Actions
workflow uploads the selected commit, applies Alembic migrations, starts PostgreSQL,
Redis, and the API, and verifies the API health endpoint.

The workflow requires the repository secret `CONSTRUCTION_OS_SERVER_PASSWORD`.
Start it manually from **Actions → Deploy staging → Run workflow**. The API and
interactive documentation are then available through
`https://185-143-145-25.sslip.io/docs`. Caddy terminates TLS and proxies requests
to the API; the API, database, and Redis container ports are not exposed publicly.
A dedicated domain is still recommended before this staging installation is
promoted to production.

## Architecture

`Project` is the aggregate anchor. Project-owned records carry `project_id`, while
`company_id` is the tenant boundary. Business modules live under `app/modules`;
shared infrastructure lives under `app/core` and `app/db`.

The first milestone intentionally contains only platform foundations and core domain
entities. Engineering calculations will be deterministic, versioned Python tools;
LLMs will only orchestrate and explain them.
