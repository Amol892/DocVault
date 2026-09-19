# DV-02 — Foundational project setup (skeleton + health check)

**Status:** implemented and verified on 2026-09-19 (branch `amol`).

## Goal
Runnable scaffold per `PRD/09-project-structure.md` and `PRD/08-deployment.md`: `docker compose up` brings up Postgres, MinIO, migrations, API and frontend. No models or tables yet. Choices: uv (backend), pnpm (frontend), skeleton + `/health` only.

## What was built
| Area | Result |
|---|---|
| Root | `docker-compose.yml` (db, storage, storage-init, migrate, api, frontend), `docker-compose.override.yml.example`, `.env.example`, README, `.editorconfig`, `.gitattributes`, `.pre-commit-config.yaml` |
| Backend | uv project, FastAPI app + `GET /health` (runs `SELECT 1`), pydantic-settings config, async SQLAlchemy session, Alembic (async env, no revisions), `StorageBackend` protocol + stub backends, placeholder `api/deps.py`, Dockerfile (non-root), pytest health test |
| Frontend | React 19 + TS strict + Vite, typed `apiFetch` client, `/api` dev proxy, App shows API status, ESLint + Prettier, Vitest + RTL (2 tests), Dockerfile |
| CI | `.github/workflows/ci.yml` (backend: ruff, mypy, alembic, pytest vs Postgres; frontend: lint, build, test) |
| Claude setup | PostToolUse auto-format hook (`.claude/hooks/format.mjs`), settings updated for uv/pnpm, `CLAUDE.md` commands + plans rule, `plans/` folder |

## Deviations from the original plan
- Worked on the existing `amol` branch (no feature branch), per instruction.
- MinIO images are `quay.io/minio/minio` and `quay.io/minio/mc`; the `minio/*` Docker Hub repos are no longer pullable.
- Versions newer than PRD 02: Vite 8, React 19.3, pnpm 12.4.2, Python 3.12 pinned (3.13 on the dev machine). TypeScript pinned to 5.9.3 (resolver offered 7.x). Frontend versions are exact; backend versions are locked in `uv.lock`.
- Postgres 18 volume mounts at `/var/lib/postgresql` (the PG18 image layout).
- CI does not run MinIO (only Postgres) since no test needs storage yet; add it with the storage FRs.
- `docker-compose.override.yml` is a local copy, git-ignored.

## Verification results (real runs)
- `docker compose up --build -d`: db and storage healthy; `migrate` and `storage-init` exited 0; api and frontend running.
- `GET localhost:8000/health` → `200 {"status":"ok","database":"ok"}`.
- `GET localhost:5173` → 200; `GET localhost:5173/api/health` (Vite proxy) → 200 with the same body.
- MinIO: bucket `docvault` present (`mc ls local`).
- Backend: `uv run pytest` 1 passed (against the compose Postgres); `ruff check` and `ruff format --check` clean; `mypy app` (strict) no issues in 19 files.
- Frontend: `pnpm lint` clean; `pnpm build` (tsc + vite) ok; `pnpm test` 2 passed.
- `.env` is git-ignored (`git check-ignore` confirmed).

## Known gaps / notes
- Running `alembic` from the host needs all settings in the environment (S3 vars etc.); inside Docker it is covered by the `migrate` service.
- Host tests must use `DATABASE_URL` pointing at `127.0.0.1:5432` with the credentials from `.env` (they can differ from `.env.example`).
- CI workflow has not yet run on GitHub.

## Next
Models + `001_init_schema` migration (PRD 04), RLS, auth/JWT, then FRs via `/plan-fr`.
