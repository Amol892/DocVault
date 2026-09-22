# DocVault

Multi-tenant document vault: workspaces, roles (Owner/Admin/Member/Guest), folders, versioned documents, share links, audit log.
Stack: FastAPI + SQLAlchemy 2 (async) + Alembic + PostgreSQL 18 + MinIO/S3 · React 19 + TypeScript + Vite · Docker Compose.

## Source of truth
The PRD lives in `PRD/` (index: `PRD/README.md`). Read only the file relevant to the task; do not load all of it.
- Feature work → find the FR in `PRD/07-functional-requirements.md` and implement exactly that.
- Any route touching workspace/folder/document → `PRD/06-permission-matrix.md` + `PRD/05-role-model.md`.
- Tables/migrations → `PRD/04-database-schema.md`. File placement → `PRD/09-project-structure.md`.
- If code and PRD disagree, or the PRD is ambiguous, stop and ask. Never silently deviate.
- Note: PRD 09 shows specs under `docs/`; in this repo they are in `PRD/`.

## Commands (update as the project gets scaffolded)
- Full stack: `cp .env.example .env` once, then `docker compose up --build` (API :8000, frontend :5173)
- Backend (from `backend/`, uv-managed): `uv run pytest` (single: `uv run pytest tests/test_x.py -k name`)
- Backend lint/format/types: `uv run ruff check . && uv run ruff format . && uv run mypy app`
- Migration: `uv run alembic revision --autogenerate -m "msg"` then `uv run alembic upgrade head` (revision files are only ever generated, never hand-edited)
- Frontend (from `frontend/`, pnpm): `pnpm dev | pnpm test | pnpm lint | pnpm build` (build runs `tsc --noEmit`)
- Backend tests use a REAL PostgreSQL: they create and use `<your database>_test` on the server `DATABASE_URL` points at (never the database itself; they refuse any name not ending in `_test`), apply the Alembic migrations to it, and empty it between tests. `DATABASE_URL` must be reachable; the API tests are in `backend/tests/`, named by risk area.
- API tests use an in-memory fake `StorageBackend` (`tests/fake_storage.py`). `tests/test_storage_backends.py` runs the real S3 backend against MinIO in a `<bucket>-test` bucket and skips itself unless MinIO answers at `S3_ENDPOINT_URL` (`docker compose up -d storage` publishes port 9000; from the host use `S3_ENDPOINT_URL=http://127.0.0.1:9000`). Email goes through the `Mailer` interface (`app/services/mailer.py`): every email is sent `multipart/alternative` (HTML from `app/templates/emails/*.html`, rendered by `services/email_templates.py` with Jinja2 autoescaping, plus a plain-text fallback). With `SMTP_HOST` unset the mailer only logs the plain-text body, so read invitation / verification / reset links from `docker compose logs api`; tests use `tests/fake_mailer.py` and run with `REQUIRE_EMAIL_VERIFICATION=false` (the verification tests switch it on). The `purge` compose service runs `app/jobs/purge.py`. Pre-signed URLs are signed for `S3_PUBLIC_ENDPOINT_URL` (the browser-reachable address); the API itself talks to `S3_ENDPOINT_URL`.

## Non-negotiable rules
1. **Authorization lives in ONE place**: `backend/app/api/deps.py`. Never re-implement role/membership checks inside a route.
2. Non-members get the same response as "not found" (no existence leaks).
3. File bytes never pass through the API: issue pre-signed URLs after the authz check. Storage only via the `StorageBackend` interface.
4. Schema changes only via Alembic migrations. Never edit an already-committed migration; add a new one.
5. Never commit secrets. Config comes from env (`pydantic-settings`); keep `.env.example` in sync.
6. Every new route needs tests, including a cross-user/cross-workspace denial case.
7. Pin exact dependency versions when adding them.

## Workflow
- Non-trivial change: plan first (Plan Mode or `/plan-fr`), get approval, then implement in small steps.
- Verify before claiming done: run tests + lint + type check and report actual output.
- One FR (or one logical unit) per branch and per commit. Commit style: `DV-XX: short imperative summary`.
- Branches: `main` (release) ← `dev` ← feature branches. Never push to `main`/`dev` directly; open a PR.
- Plans: once a plan is fully implemented AND verified (tests/lint/run green), save it in `plans/<DV-XX>-<slug>.md` reflecting the final state (deviations + real verification results) and index it in `plans/README.md`. Never save a plan before it is verified; update it if the work later changes.
- Prefer editing existing files over creating new ones; follow `PRD/09-project-structure.md` layout.

## Code style
- Python: type hints everywhere, async I/O, Pydantic v2 schemas for all request/response bodies, thin route handlers.
- TypeScript: `strict`, no `any`, typed API client in `frontend/src/api/`.
- Match surrounding code; don't add comments that restate the code.

More detailed, path-scoped rules are in `.claude/rules/`.
