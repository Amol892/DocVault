# DV-06 — Backend API: folders, documents, object storage (+ minimal folder UI)

**Status:** implemented and verified on 2026-09-20 (branch `document-features`, uncommitted).

## Goal
Implement the folders and documents parts of `PRD/10-api-specification.md` (FR-5..9, FR-21..24) and the object-storage layer behind them, so the UI stops getting 404 for `/workspaces/{id}/folders`, `/documents` and `/documents/upload-url`. Invites, share links, the activity endpoint, restore and purge jobs stay out of scope.

## Decisions
- Scope: folders + documents (chosen by the user). Tests: fake in-memory storage for the API tests **plus** a separate file exercising the real S3 backend against MinIO. Frontend: minimal folder create / rename / delete now.
- **No schema change, no migration.** The current version of a document is its highest-numbered `ready` version, so a pending or rejected re-upload never hides the previous file. `alembic check` in the test setup proves models still match the migrations.
- Presigned URLs are signed for `S3_PUBLIC_ENDPOINT_URL` (browser-reachable, `http://localhost:9000` in dev) because a SigV4 signature covers the host; the API itself uses `S3_ENDPOINT_URL` (`http://storage:9000` in Docker) for HEAD, ranged GET and DELETE.
- Storage keys are server-generated and opaque: `w/<workspace>/<document>/<version>` or `u/<user>/<document>/<version>` (FR-6).
- Uploads are validated at confirm time from what storage reports, not from what the client says: stored size and content type must equal the declared ones, executables (PE, ELF, Mach-O, shebang) are refused whatever they claim, and PDF / image / Office / ZIP types must start with the matching magic bytes. Rejection marks the version `rejected`, deletes the object and soft-deletes a document that has no ready version.
- Folder delete (FR-23) is a soft delete that re-parents child folders and documents to the deleted folder's parent (renaming `name (moved N)` on a sibling clash) and removes grants on it.
- A Guest's folder list, document list and every folder/document endpoint are scoped on the server (recursive CTE: granted folders and their descendants). A guest addressing anything outside that gets the same 404 as a missing id; a guest with a grant who tries to write gets 403.

## What was built
| Area | Result |
|---|---|
| Storage | `storage/base.py` (`StorageBackend` protocol, `ObjectInfo`, safe `content_disposition`), `storage/s3_backend.py` (aioboto3, SigV4, path-style; upload URLs sign `Content-Type` and `Content-Length`, 15 min; download URLs 5 min, forced `attachment`), `storage/__init__.py` (`get_storage`; `local` raises a clear config error) |
| Config | `s3_public_endpoint_url`, `s3_region`, URL lifetimes; compose publishes MinIO 9000 and sets `S3_PUBLIC_ENDPOINT_URL`; `.env.example`; CI starts MinIO |
| Authorization | `services/access.py` (loaders returning None for every kind of "no"), `api/deps.py` additions: `get_folder_access`, `require_folder`, `get_document_access`, `require_document`, `get_upload_target`, `get_list_scope` |
| Folders | `services/folders.py`, `api/routes/folders.py`: list, create (parent must be live in this workspace, depth cap 20, case-insensitive sibling uniqueness -> `NAME_TAKEN`), rename, delete, grant / revoke (Admin+, Guests only, idempotent, logged) |
| Documents | `services/documents.py`, `services/upload_validation.py`, `api/routes/documents.py`: list + search (filename or uploader, LIKE-escaped), upload-url (new document or new version via `document_id`, `413 FILE_TOO_LARGE`), confirm-upload (idempotent), download-url, rename / move, soft delete |
| Frontend | `Sidebar` shows exactly the server-scoped list (client-side guest filtering and `guestCanSeeFolder` removed); Member+ get "+ New folder", rename and delete with confirmation, errors as toasts; a profile menu (`UserMenu`: name, email, Sign out) at the bottom of the sidebar and on the workspaces page; Sign out calls `logout` (server-side token revocation). Read-only: editing a profile needs an API and a PRD entry that do not exist yet |
| Docs | `PRD/10-api-specification.md`, `PRD/08-deployment.md`, `CLAUDE.md`, frontend README |

## Deviations from the plan
- The folder UI creates folders at the workspace root only (no nested-folder creation or folder moving from the UI); the API supports nesting.
- A file that fails validation and belongs to a brand-new document soft-deletes that document (not in the original plan; avoids an empty listed document).
- Tests import `tests.fake_storage`; helpers `make_folder` and `upload_document` were added to `tests/helpers.py`.

## Verification (real runs)
- Backend: `ruff check`, `ruff format --check`, `mypy app` (strict, 48 files) clean. **356 tests: 351 pass, 5 skipped** by default (the MinIO tests skip when MinIO is not reachable at `S3_ENDPOINT_URL`, as with a Docker-oriented `.env`); with `S3_ENDPOINT_URL=http://127.0.0.1:9000` the storage tests pass 6 of 6 against the real MinIO. `alembic check` passes (no migration).
- **Mutation check:** ten deliberate breakages (guest filter dropped in the folder list and in the document list, guests seeing every folder, personal-document owner check skipped, guests allowed to upload, size / content-type verification skipped, executable refusal skipped, non-Guest grant allowed, search wildcards not escaped) were each caught by the tests; files restored.
- **Live end-to-end run:** the real API on the test database and the real MinIO, driven over HTTP acting as the browser: 31 of 31 checks (folder create and duplicate 409, upload-url, CORS preflight on the presigned URL, confirm before upload 409, PUT straight to MinIO, confirm, list, search by filename and uploader, download bytes equal, forced attachment, executable refused and object deleted, MinIO refusing a wrong Content-Type, new version 2 becoming current, rename, move, outsider and ungranted guest 404, grant, guest read-only 403, server-scoped guest folder list, immediate revocation, folder delete relocating the document, soft delete).
- Frontend: `lint`, `build` (`tsc`), `prettier` clean; **63 of 63 tests**; the frontend's own `foldersApi` / `documentsApi` modules run against the live backend: 10 of 10 checks (including the real presigned PUT and confirm).
- `docker compose build api` succeeds; the recreated `api` container answers `/health`, and `/api/v1/workspaces/x/folders` and `/api/v1/documents` now answer 401 (unauthenticated) instead of the earlier 404.

## Known follow-ups
- Invites and acceptance, share links (and their public endpoints), the activity endpoint.
- Restore of soft-deleted documents/folders and a purge job (soft-deleted objects, stale `pending` uploads and rejected versions are left in place for now).
- Local-disk `StorageBackend`, SHA-256 checksums, virus scanning, thumbnails, moving folders, a version-history UI.
- Production: MinIO/S3 must be reachable by browsers over TLS at `S3_PUBLIC_ENDPOINT_URL`, with CORS allowing the frontend origin (MinIO's defaults were verified in the live run).

## To apply
No migration. Recreate the API container (`docker compose up -d --no-deps api`) to pick up the new code and env. Run `docker compose up -d storage` once so MinIO publishes port 9000.
