# Database migrations (Alembic)

Schema changes to PostgreSQL happen **only** through the revisions in [`versions/`](versions/). Never run manual DDL against a running database.

The models in [`backend/app/models/`](../app/models/) are the source of truth. Alembic compares them with the live database (`--autogenerate`) and writes a revision that closes the gap. The design behind the models is in [`PRD/04-database-schema.md`](../../PRD/04-database-schema.md).

## How it is wired

| Piece | Where | Notes |
|---|---|---|
| Config | `backend/alembic.ini` | Sets the script location, date-prefixed file names (`2026_09_19_1030-<rev>_<slug>.py`) and logging. No database URL. |
| Environment | `alembic/env.py` | Async engine (`asyncpg`), `NullPool`. Reads `DATABASE_URL` through `app.config.Settings`, so it uses the same environment as the API. Supports online and offline (`--sql`) mode. |
| Metadata | `app.db.base.Base.metadata` | Complete only because `env.py` imports `app.models`. **A new model must be imported in `app/models/__init__.py`, or autogenerate will not see it.** |
| Constraint names | `NAMING_CONVENTION` in `app/db/base.py` | Deterministic names (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`), so revisions are stable and constraints can be dropped by name. |
| Template | `alembic/script.py.mako` | Layout of new revision files. |
| Docker | `migrate` service in `docker-compose.yml` | One-shot `alembic upgrade head`; the `api` service waits for it to finish. |

## Commands

Run from `backend/`. The database must be reachable through `DATABASE_URL` (see below).

```bash
uv run alembic revision --autogenerate -m "short description"   # create a revision from model changes
uv run alembic upgrade head                                     # apply all pending revisions
uv run alembic downgrade -1                                     # undo the last revision
uv run alembic current                                          # revision the database is at
uv run alembic history --verbose                                # all revisions
uv run alembic heads                                            # latest revision(s); must be exactly one
uv run alembic upgrade head --sql                               # print the SQL without touching a database
```

With Docker, `docker compose up` applies pending revisions automatically through the `migrate` service.

### Which database URL?

Settings live in one place, the repo-root `.env`, and are read wherever you run the command from (real environment variables win over the file). There is no `backend/.env`.

`DATABASE_URL` in the root `.env` is written for tools on your machine, so its host is `127.0.0.1`, not `db`. The name `db` only exists inside Docker's network. Docker Compose overrides `DATABASE_URL` for the `migrate` and `api` containers, so the same file works for both.

To run Alembic on your machine:

1. Publish the database port: `cp docker-compose.override.yml.example docker-compose.override.yml`, then `docker compose up -d db`.
2. In the root `.env`, make sure `DATABASE_URL` looks like `postgresql+asyncpg://<user>:<password>@127.0.0.1:5433/<database>`, using the same values as `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`. Use `127.0.0.1` rather than `localhost`, which can resolve to IPv6 and reach a different service. Do not leave the database name off the end. The port is **5433**: the container's port is published there so it cannot clash with a PostgreSQL installed on your machine (which would receive the connection instead).

| Where it runs | Host | Comes from |
|---|---|---|
| On your machine (Alembic, pytest, uvicorn) | `127.0.0.1` | root `.env` |
| Inside Docker (`migrate`, `api`) | `db` | override in `docker-compose.yml` |

## Workflow for a schema change

1. Change or add the model (and import it in `app/models/__init__.py` if it is new).
2. `uv run alembic revision --autogenerate -m "add <thing>"`.
3. **Read the generated file** (and preview it with `upgrade head --sql`). Do not edit it: if something is wrong, fix the model and regenerate (see below).
4. `uv run alembic upgrade head`, then `uv run alembic downgrade -1`, then `upgrade head` again to prove the revision round-trips.
5. Commit the model change and the revision together.

## What autogenerate cannot do (and how the models cope)

**Revision files are only ever produced by `alembic revision --autogenerate`. Never edit one by hand.** If a generated revision is wrong, fix the **model** and regenerate: delete the unapplied revision file, then run the command again. (If the revision was already applied, run `alembic downgrade` first, or add a new revision instead.)

So the models are written to be self-sufficient for autogenerate. These are known gaps, and the models avoid them on purpose:

- **Native PostgreSQL enum types.** Autogenerate creates them with the table but `downgrade` never drops them, and one type shared by two tables makes `create_table` run `CREATE TYPE` twice. Enums are therefore stored as `VARCHAR` plus a named CHECK constraint (`db_enum()` in `app/models/enums.py`). Do not add a native enum.
- **Circular foreign keys.** A `use_alter=True` constraint is silently **dropped** from `create_table` and never created. Keep the foreign-key graph acyclic. This is why `documents` has no `current_version_id`: the current version is the row in `document_versions` with the highest `version_number`.
- **Extensions, functions, triggers, RLS policies, roles.** Alembic never generates them, so the models do not depend on any (ids are generated in Python, email uniqueness uses a `lower(email)` index, not `citext`). The integrity triggers and Row-Level Security in the design are planned but **not implemented**, because they cannot be produced by autogenerate.
- **Renames.** A renamed column or table looks like a drop plus an add and would lose data. Plan renames deliberately before generating.
- **Server-default and `NOT NULL` changes on tables that already hold rows.** Add the column as nullable and backfill in a separate step before tightening.
- **Functional and partial indexes** (`lower(email)`, `WHERE deleted_at IS NULL`, `NULLS NOT DISTINCT`) are rendered by autogenerate; confirm the expression text in the generated file.

To inspect what a revision will do without touching a database, run `uv run alembic upgrade head --sql` (and `uv run alembic downgrade <rev>:base --sql`). Check that every foreign key is created, the downgrade drops tables in reverse dependency order, and there is no leftover `CREATE TYPE`.

## Rules

- **Never edit a revision that has been merged or applied anywhere else.** Add a new one.
- Every revision must be reversible (`downgrade()` works) unless there is a documented reason.
- One logical change per revision, with a descriptive message.
- `heads` must show a single head. If two branches created revisions in parallel, merge them with `alembic merge heads -m "merge"`.
- Never put secrets or environment-specific values in a revision.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run the command from `backend/`. `alembic.ini` uses `prepend_sys_path = .` |
| `ValidationError ... Field required` (Settings) | A required variable is missing: `DATABASE_URL`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `JWT_SECRET`. They are read from the repo-root `.env` (copy `.env.example` there if it does not exist) or the environment. |
| `getaddrinfo failed` / cannot resolve `db` | The root `.env` still uses the Docker host name. Change `DATABASE_URL` to use `127.0.0.1` (see "Which database URL?"). |
| `database "<name>" does not exist` | You reached a different PostgreSQL than the container, usually one installed on your machine on port 5432. The compose database always creates `POSTGRES_DB` on first start. Use port 5433 (see "Which database URL?") and check `docker compose ps db` shows `5433->5432`. |
| `password authentication failed` / connection refused | Wrong user, password, port or database in `DATABASE_URL`, or the database container is not running / its port is not published. |
| Autogenerate produces an empty revision | The model is not imported in `app/models/__init__.py`, or the database is already up to date. |
| `Target database is not up to date` | Run `uv run alembic upgrade head` before creating a new revision. |
| `Can't locate revision identified by ...` | The database points at a revision that is not in `versions/` (for example after switching branches). Check `alembic history`. |
