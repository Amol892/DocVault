# 02 — Technology Stack

| Layer | Choice | Stable version (pin at build time) |
|---|---|---|
| Language (backend) | Python | 3.12.x (3.13 acceptable if all deps confirmed compatible) |
| Backend framework | FastAPI | 0.136.x |
| ASGI server | Uvicorn | 0.34.x |
| Data validation | Pydantic | 2.x (v2 line, ships with FastAPI) |
| ORM | SQLAlchemy | 2.x (async engine) |
| Migrations | Alembic | 1.14.x |
| Database | PostgreSQL | 18.x (17.x is an acceptable fallback if a managed provider hasn't caught up) |
| Object storage | MinIO (S3-compatible) | latest stable `RELEASE` image locally; any S3-compatible provider in production via the same client |
| Storage SDK | `boto3` / `aioboto3` | latest stable, S3-compatible API only (no AWS-specific features used) |
| Auth | JWT (`python-jose` or `pyjwt`) + `passlib[argon2]` | latest stable |
| Frontend language | TypeScript | 5.x |
| Frontend framework | React | 19.2.x |
| Frontend build tool | Vite | 6.x |
| Frontend HTTP client | native `fetch` or `axios` | latest stable |
| Package manager (frontend) | pnpm or npm | Node 22.x LTS (Maintenance) or 24.x LTS (Active) as the runtime |
| Containerization | Docker + Docker Compose | Compose v2 (`docker compose`, not the standalone v1 binary) |
| Testing (backend) | pytest + httpx (async test client) | latest stable |
| Testing (frontend) | Vitest + React Testing Library | latest stable |

**Constraint compliance check:** Python ✅, PostgreSQL with migrations (Alembic) ✅, storage kept out of Postgres and behind an S3-compatible abstraction (MinIO swappable for real S3/local disk) ✅, React + TypeScript UI ✅, FastAPI backend ✅, single `docker-compose up` bring-up ✅.

**Note:** treat these as of the last time this doc was written — pin exact patch versions in `pyproject.toml`/`package.json` at actual implementation time rather than trusting this table to stay current.

Related: [08-deployment.md](./08-deployment.md) for how these pieces run together, [09-project-structure.md](./09-project-structure.md) for where each lives in the repo.
