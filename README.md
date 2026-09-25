# DocVault

Multi-tenant document vault: workspaces, roles (Owner / Admin / Member / Guest), folders, versioned documents, share links and an audit log.

**Stack:** FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 18 · MinIO/S3 · React 19 · TypeScript · Vite · Docker Compose.

This README is the submission document for the *File Storage & Sharing* take-home assignment: how to run it, how it's built, every gap in the brief and the call I made on it, the security posture, the product improvement I chose, and how I worked with my coding agent. The full product spec lives in [PRD/](PRD/README.md), day-to-day usage in [USER_GUIDE.md](USER_GUIDE.md), a sequential code walkthrough in [PROCESS_FLOW.md](PROCESS_FLOW.md), and a verified, dated record of every implementation slice in [plans/](plans/README.md).

## Contents

1. [Quick start](#quick-start)
2. [Architecture overview](#architecture-overview)
3. [Assumptions and decisions](#assumptions-and-decisions)
4. [Security considerations](#security-considerations)
5. [Product improvement](#product-improvement)
6. [How I worked with my coding agent](#how-i-worked-with-my-coding-agent)
7. [What I'd do next with more time](#what-id-do-next-with-more-time)

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

That's the whole stack: Postgres, MinIO, a one-shot migration runner, the API, the frontend, and an hourly housekeeping job — nothing else to install. First boot to a working sign-up page is under 5 minutes on a machine that already has Docker.

### Development without Docker

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

Backend settings come from real environment variables, then the repo-root `.env`, wherever you run the command from. The root `.env` is written for tools on your machine, so `DATABASE_URL` uses `127.0.0.1` (the database port is published by `docker-compose.override.yml`). Docker Compose overrides `DATABASE_URL` and `S3_ENDPOINT_URL` for the containers, so the same `.env` works for both.

With `SMTP_HOST` unset (the `.env.example` default), the mailer just logs each email's plain-text body — read invitation / verification / reset links from `docker compose logs api`.

## Architecture overview

```
backend/    FastAPI app, Alembic migrations, tests
frontend/   React + TypeScript SPA
PRD/        product specification (one file per concern)
plans/      implemented-and-verified plans, one per task
.claude/    Claude Code project setup (rules, commands, agents, hooks)
```

**Request flow:** browser → typed API client (`frontend/src/api/`) → FastAPI route (`backend/app/api/routes/`, kept thin) → the single authorization choke point (`backend/app/api/deps.py`) → a service module (`backend/app/services/`) for the actual business logic → SQLAlchemy models (`backend/app/models/`). File bytes never go through this path at all — see [Security considerations](#security-considerations).

**Backend layout** (`backend/app/`):

| Module | Responsibility |
|---|---|
| `api/routes/` | One thin router per resource: `auth`, `workspaces`, `members`, `invites`, `folders`, `documents`, `share_links`, `public`, `activity`, `health` |
| `api/deps.py` | The only place role/membership/ownership checks live — routes depend on this, never re-implement checks |
| `services/` | Business logic: `accounts`, `account_recovery`, `access` (authorization loaders), `workspaces`, `folders`, `documents`, `share_links`, `invites`, `upload_validation`, `activity`, `mailer` + `email_templates`, `preview`, `purge` |
| `models/` | One SQLAlchemy 2 model module per entity: `user`, `workspace` (+ membership), `folder`, `document` (+ versions, grants), `share_link` (+ access log), `activity`, `auth_token`, `revoked_token` |
| `schemas/` | Pydantic v2 request/response schemas, mirrored 1:1 in `frontend/src/types/` |
| `storage/` | `StorageBackend` protocol with an S3/MinIO implementation and a local-disk implementation behind the same interface |
| `core/` | `security.py` (hashing + JWT), `permissions.py` (the role→action matrix), `errors.py`, `ids.py`, `logging.py` |
| `jobs/purge.py` | Trash grace-period purge, abandoned-upload cleanup, expired revoked-token cleanup — runs as its own compose service |

**Frontend layout** (`frontend/src/`): `api/` (typed fetch wrappers, one per backend resource), `pages/` (routed views), `components/` (reusable UI, including modals for upload/share/versions/preview), `auth/` (session context + route guarding), `permissions/roleHierarchy.ts` (client-side mirror of the role matrix, for hiding/disabling actions only — never the enforcement point), `workspace/` (active-workspace context), `hooks/`.

**Docker Compose services:** `db` (Postgres 18), `storage` (MinIO, S3 API on 9000 — the browser talks to it directly via pre-signed URLs, never through the API), `storage-init` (one-shot bucket creation), `migrate` (one-shot `alembic upgrade head`), `api`, `frontend`, and `purge` (hourly housekeeping job, `restart: unless-stopped`).

Full detail, including the ERD and permission matrix, is in [PRD/03-architecture.md](PRD/03-architecture.md), [PRD/04-database-schema.md](PRD/04-database-schema.md) and [PRD/06-permission-matrix.md](PRD/06-permission-matrix.md).

## Assumptions and decisions

The brief was deliberately incomplete. Here's every gap I filled, what I chose, and why — this is the section I'd want a reviewer to read most carefully.

**Role model.** Four roles per workspace — Owner (exactly one, transferable, can't leave without transferring), Admin, Member, Guest — rather than a flatter "owner/collaborator" split. A team asking for a "workspace" in the brief implied internal structure (who can invite, who can delete a folder, who's just there to view one thing), so I modeled it explicitly instead of bolting permission checks onto an undifferentiated member list. The full matrix is [PRD/06-permission-matrix.md](PRD/06-permission-matrix.md).

**Guest access is document-level, not folder-level.** My first pass gave Guests access to whole granted folders (and their descendants), which is what most similar products do. Testing it as a user, it was the wrong default for "share with someone outside the team": a Guest is usually there for *one* document, not a whole folder's worth of unrelated files that happened to land next to it. I replaced folder-based guest grants with a `document_grants` table — an Admin+ grants a Guest access to one document at a time, revoked immediately if the document moves to a different folder ("folder-pinned" grants — see [plans/DV-08](plans/DV-08-guest-document-level-access.md) for the full rationale and migration). Guests have no visibility into folders at all, even ones containing a document they can see.

**Invites for people without an account yet.** An invite is an emailed token tied to a role and (for Guests) specific documents. Opening the link when you don't have an account routes you through sign-up first, then straight to acceptance with the invited role already applied — you never land on "create your own workspace" by mistake (an early real bug I hit and fixed; see [How I worked with my coding agent](#how-i-worked-with-my-coding-agent)). Opening it as the wrong signed-in account shows that plainly, with a sign-out option, rather than a bare 403.

**What a share link can do.** FR-12 left this open, so a link is: no account required to open it; an optional password; an optional expiry date; and a toggle for whether the recipient can download the file or only view it inline (both changeable after the link is created, not just at creation — see [Product improvement](#product-improvement)). Revoking is immediate and checked on every access, never cached. Every access attempt — success, wrong password, expired, revoked — is logged with IP and outcome for the owner to review (FR-14).

**Versioning, not overwrite.** Re-uploading a document creates a new `document_versions` row; the "current" version is the highest-numbered `ready` one, so a pending re-upload never hides the previous file mid-way. Old versions stay downloadable individually.

**Deletion is soft, with a grace period, then a background purge.** Deleting a document or folder sets `deleted_at` rather than removing anything, so it's a mistake you can undo. A folder delete re-parents its children to the folder's own parent (or the root) instead of cascading the delete — losing a folder shouldn't silently disappear everything inside it. An hourly job (`app/jobs/purge.py`) removes documents past the grace period, storage objects for abandoned (never-confirmed) uploads, and expired revoked-token rows.

**File size limit and upload validation.** 100 MB default cap (configurable), because this is a document vault, not a media host. Beyond a size and declared-MIME check, the API re-reads what actually landed in storage and does magic-byte sniffing to catch content that doesn't match what it claims to be, and unconditionally rejects anything that looks like an executable (PE/ELF/Mach-O/shebang) regardless of declared type. It's explicitly not virus scanning — see [Security considerations](#security-considerations).

**Auth approach.** Email + password with Argon2 hashing, a bearer JWT (24h, no refresh flow — expiry just means logging in again, which is an acceptable trade-off for this scope), and per-token revocation on logout via a `jti` blocklist rather than a stateless "trust every unexpired token" design. Email verification is required before anything beyond `/auth/me` works, closing the obvious "invite a fake address" hole. I chose this over OAuth/social login because the brief's users are an internal team plus outside recipients of a link — a third-party identity provider adds setup friction for evaluators without buying much for this scope.

**API shape.** REST, JSON in/out, Pydantic v2 schemas on every route (both directions), typed one-to-one on the frontend in `src/types/`. No GraphQL — the domain is a handful of well-defined resources with no need for client-composed queries.

**Storage abstraction.** A `StorageBackend` protocol with the required S3/MinIO implementation and a local-disk one behind the same interface, so swapping is a config value, not a rewrite — per the brief's constraint.

## Security considerations

**Addressed:**
- Passwords hashed with Argon2 (`passlib`); a dummy hash is verified on login for an unknown email so response timing doesn't reveal which addresses have accounts.
- JWTs are HS256, signed with a secret pinned to ≥32 chars at startup, decoded with the algorithm list pinned (`algorithms=["HS256"]`) to reject `alg: none` / algorithm-confusion attacks. Every token carries a random 128-bit `jti`; logout revokes that specific token via a `revoked_tokens` table checked on every authenticated request, and the hourly purge job cleans up expired revocation rows so the table doesn't grow unbounded.
- **No existence leaks, anywhere.** A non-member of a workspace, someone addressing another user's personal document, and a genuinely missing id all get byte-identical 404s — proven by the code path itself: `get_workspace_access`/`get_document_access`/`get_folder_access` in `api/deps.py` do one query each and return `None` for every "no" case uniformly (missing, deleted, not-a-member, ungranted Guest); `deps.py` turns every `None` into the same 404. A 403 is only ever raised once membership is already established and it's a real "your role can't do this" case.
- File bytes never pass through the API. Uploads and downloads go directly between the browser and MinIO/S3 via pre-signed URLs (upload URLs expire in 15 min, download/preview URLs in 5 min); storage credentials exist only server-side and are never returned to a client. Upload URLs bind the declared content-type and size into the signature, so the browser can't PUT something else under a stolen URL.
- Share link tokens are `secrets.token_urlsafe(32)` — 256 bits of entropy — and only their SHA-256 hash is stored, so a database leak doesn't hand out working links. Password-protected links lock out after 10 bad attempts per link+IP within 15 minutes. Public share URLs get their own short (5 min) expiry, separate from the authenticated download/preview URLs.
- Upload validation re-derives the truth from storage (HEAD + first bytes) rather than trusting client-declared metadata: size match, content-type match, magic-byte sniffing against the declared type, and unconditional rejection of anything that looks like an executable.

**Knowingly left out (and why):**
- **No login rate limiting / lockout.** Argon2's cost factor slows brute force, but there's no IP- or account-based throttle on `/auth/login` itself. This is the gap I'd close first with more time — it's a real, named risk for a public-facing deployment, just out of scope for a weekend build focused on the sharing/workspace flows the brief cared most about. (The resend-cooldown on verification/reset emails is a different, narrower throttle and doesn't cover this.)
- **No refresh-token flow or "log out everywhere."** Logout revokes the one token used for that request, not every session for the user. Acceptable for this scope; a real deployment would want a session-revocation-on-password-change path.
- **DB-level integrity is not fully redundant with the application layer yet.** Things like "a workspace always has exactly one Owner" and "a finalized document version is immutable" are enforced by the service layer and (for the Owner invariant) a partial unique index, but not yet by Postgres triggers/roles that would hold even if a bug bypassed the application layer entirely. Documented as "planned" in [PRD/04-database-schema.md](PRD/04-database-schema.md).
- **No virus/malware scanning.** Upload validation catches file-type spoofing and outright executables, but it is explicitly not antivirus — nothing inspects file content for malicious payloads inside an otherwise-valid PDF/image/document.
- **No CSRF-specific protection**, but this is a bearer-token JSON API (no cookie-based session), which is the usual reason CSRF doesn't apply — flagging it here rather than silently omitting it.

## Product improvement

I chose to **build** an editable share-link download toggle plus in-app inline document preview, rather than write a design note, because it came directly from using the product myself: sharing a document at that point meant handing someone a link that always let them download the file, and there was no way to just let someone *look* at something without also giving them a saved copy — the "share externally" flow from the brief only had one mode.

- `PATCH /share-links/{id}` lets the owner flip `allow_download` on an already-issued link without revoking it (the token/URL never changes), logged to the activity feed only when the value actually changes.
- `GET /documents/{id}/preview-url` and the equivalent public share-link path return a short-lived pre-signed URL with `Content-Disposition: inline` for previewable types (PDF, PNG, JPEG, GIF, WebP, plain text); the frontend renders it in an in-app modal (click the document's name or its **View** button) instead of forcing a download-and-open-locally round trip.
- Access rules are identical to download — a Guest without a grant, or an outsider without the link, gets the same 404/410 as before; this only changes *what* an already-authorized viewer can do, not *who* is authorized.

Full detail, deviations and verification are in [plans/DV-09](plans/DV-09-editable-share-download-and-inline-preview.md). I'd also flag [plans/DV-08](plans/DV-08-guest-document-level-access.md) (Guest access moved from folder-level to document-level) as a second, more foundational product call worth reading — it's a correctness/scope fix rather than a net-new feature, so I didn't count it as *the* improvement, but it changed the security posture of external sharing more than DV-09 did.

Other directions I considered and set aside for time: full-text search across documents, per-workspace storage quotas, and notifications on share-link access — all listed as candidates in [Known follow-ups](plans/README.md) rather than built.

## How I worked with my coding agent

I used **Claude Code** for essentially all of the implementation, working from a written spec I built up front (an initial brainstorming and requirements pass, [shared here](https://claude.ai/share/55f05a32-04db-42f1-bb58-ed3c0261d3fd)), turned into the versioned [PRD/](PRD/README.md) that the agent was told to treat as the single source of truth — "if code and the PRD disagree, or the PRD is ambiguous, stop and ask; never silently deviate" is a standing rule in [CLAUDE.md](CLAUDE.md).

**What I delegated:** almost all boilerplate and first-draft implementation — models, migrations, routes, services, tests, and the React UI — one functional requirement (or one clearly-scoped follow-up) at a time, each on its own branch, planned before code with an explicit approval step. I also had it run its own **mutation testing** pass on every authorization-sensitive change: deliberately break the check (skip the ownership guard, skip the Guest-grant check, let a non-member through) and confirm the test suite actually catches it, not just that tests pass on the correct code.

**Where it went wrong, and how I caught it:**
- A `SMTPSenderRefused` error traced back to a malformed `SMTP_FROM` value with no code-level validation — I had the agent add fail-fast startup validation (a Pydantic field validator) instead of a one-off fix, since the same misconfiguration would otherwise silently break every outgoing email again later.
- A real, user-visible bug: accepting a workspace invite as Admin/Member/Guest was actually landing people on "create a new workspace," because the accept button stayed clickable for a signed-in-as-the-wrong-account or unverified state, and a failed accept reused the same UI state as "this link is permanently dead" — discarding the real reason and pointing the user away from recovery. I found this by directly querying the database (zero `member.joined` activity rows, invites all ending up revoked) rather than trusting that "the endpoint returns 200 in tests" meant the flow worked end-to-end, and had the agent separate the error states and disable the button pre-emptively with an explanation instead.
- An autogenerated Alembic migration for the DV-08 guest-access change created a table before the unique constraint its foreign key depended on, failing on `alembic upgrade head`. I reviewed the generated output (permitted, since the migration had never been applied anywhere — never for an already-merged one) and had the agent reorder the two statements rather than regenerate blindly.
- A few of my own end-to-end verification scripts had bugs in the assertions themselves (e.g. checking for a 403 after I'd already revoked the access that would have produced one, instead of a 404) — caught by the check failing for a reason that didn't match the code, not by trusting the first "FAIL" line at face value.

I ran everything the agent produced myself: real Postgres for tests (not sqlite), real MinIO for the storage backend tests, and standalone end-to-end scripts driving the running API like a browser would, in addition to unit/integration tests — because a green unit-test suite doesn't prove a presigned URL is actually reachable in a browser, or that dev SMTP is actually deliverable to a real inbox. Nothing was committed or merged without me reviewing the diff first.

## What I'd do next with more time

- Login rate limiting/lockout (the security gap I'd close first — see above).
- Refresh tokens and a "log out everywhere" action on password change.
- DB-level enforcement (triggers, a least-privilege app role) for the invariants currently held only by the application layer.
- Full-text search across document content, not just filename/uploader.
- Per-workspace storage quotas and usage reporting.
- Notifications (email or in-app) when a share link is accessed or a document is updated.
- Inline preview for Office formats (`.docx`/`.xlsx`/`.pptx`), currently outside the small previewable-type allowlist.

---

Working with Claude Code? Read [CLAUDE.md](CLAUDE.md) first.
