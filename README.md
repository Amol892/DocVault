# DocVault

Multi-tenant document vault: workspaces, roles (Owner / Admin / Member / Guest), folders, versioned documents, share links and an audit log.

**Stack:** FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 18 · MinIO/S3 · React 19 · TypeScript · Vite · Docker Compose.

The product specification lives in [PRD/](PRD/README.md). Implementation plans live in [plans/](plans/README.md).

## Quick start

```bash
cp .env.example .env        # works unedited for local dev
cp docker-compose.override.yml.example docker-compose.override.yml   # optional: MinIO console, hot reload
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 (docs at `/docs`, health at `/health`) |
| MinIO console | http://localhost:9001 (override file only) |

## Development without Docker

Requires [uv](https://docs.astral.sh/uv/), Node 24 and pnpm 12. Run `docker compose up db storage storage-init` for the dependencies (with the override file so the DB port is exposed), then:

```bash
# backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest && uv run ruff check . && uv run mypy app

# frontend
cd frontend
pnpm install
pnpm dev
pnpm test && pnpm lint && pnpm build
```

Backend settings are read from environment variables or a `.env` file in `backend/` (see `.env.example`; use `localhost` instead of the compose hostnames).

## Layout

```
backend/    FastAPI app, Alembic migrations, tests
frontend/   React + TypeScript SPA
PRD/        product specification (one file per concern)
plans/      implemented-and-verified plans, one per task
.claude/    Claude Code project setup (rules, commands, agents, hooks)
```

Working with Claude Code? Read [CLAUDE.md](CLAUDE.md) first.
