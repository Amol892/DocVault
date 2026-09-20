# 10 — API Specification (frontend contract)

> **Status: draft contract.** This is the REST API the React client in `frontend/` is written against. The backend does not implement it yet (only `GET /health` exists), so treat this file as the specification the backend tasks must satisfy, or amend it, in the same change as the client (`frontend/src/api/`, `frontend/src/types/index.ts`).

## Conventions

- **Base path:** `/api/v1`. In development the Vite server proxies `/api` to the API, so the backend must mount its routers under `/api/v1` (or the proxy must rewrite).
- **Auth:** `Authorization: Bearer <JWT>` on every request except `POST /auth/register`, `POST /auth/login` and the public share endpoints. Tokens are short-lived (FR-3). A `401` on an authenticated request means the session is gone; the client drops it and returns to the login page.
- **Ids** are opaque 12-character strings (`RandomIdMixin`). Never assume a format, order or UUID.
- **Errors:** every non-2xx response is `{ "error": { "code": "<STABLE_CODE>", "message": "<safe to show a user>" } }`. `message` must never leak whether a resource the caller cannot access exists: use `404` for both "missing" and "not yours" (PRD 06).
- **Authorization** is enforced by the server on every call (`api/deps.py`, PRD 06). The "Role" column below is the minimum role; the client hides controls accordingly but is never the enforcement point.
- **Pagination:** `Paginated<T> = { items: T[], page: number, total: number }`, `page` starts at 1.
- **Timestamps** are ISO 8601 UTC strings.

## Endpoints

### Auth (FR-1..3)

| Method & path | Body → Response | Role |
|---|---|---|
| `POST /auth/register` | `{ email, password, name }` → `User` | public |
| `POST /auth/login` | `{ email, password }` → `{ token, user: User }` | public |
| `GET /auth/me` | → `User` | any signed-in user |

Email verification and password reset (FR-1, FR-4) have no storage in the schema (removed by decision), so there are no endpoints for them yet.

### Workspaces and members (FR-16..21)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /workspaces` | → `WorkspaceSummary[]` (only workspaces the caller belongs to, FR-17) | any |
| `POST /workspaces` | `{ name }` → `Workspace`; the caller becomes Owner | any |
| `GET /workspaces/{id}` | → `Workspace` | member of it |
| `DELETE /workspaces/{id}` | → 204 | Owner |
| `GET /workspaces/{id}/members` | → `WorkspaceMember[]` (guests include `granted_folder_ids`) | Member+ |
| `PATCH /workspaces/{id}/members/{userId}` | `{ role }` → 204 | Admin+ (never the Owner row) |
| `DELETE /workspaces/{id}/members/{userId}` | → 204; access is revoked immediately (FR-19) | Admin+ (never the Owner row) |
| `POST /workspaces/{id}/members/{userId}/transfer-ownership` | → 204 | Owner |
| `POST /workspaces/{id}/invites` | `{ email, role: "admin"\|"member"\|"guest" }` → `WorkspaceInvite` | Admin+ |
| `POST /invites/{token}/accept` | → 204 | the invited user |

A workspace always has exactly one Owner (FR-20); `role: "owner"` is never accepted by an invite or a role change.

### Folders (FR-21..23)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /workspaces/{id}/folders` | → `Folder[]`; a Guest gets only granted folders and their descendants | any member |
| `POST /workspaces/{id}/folders` | `{ name, parent_folder_id }` → `Folder` | Member+ |
| `PATCH /folders/{id}` | `{ name }` → `Folder` | Member+ |
| `DELETE /folders/{id}` | → 204; its documents are relocated or flagged, never deleted (FR-23) | Member+ |
| `POST /folders/{id}/grants` | `{ user_id }` → 204; the user must be a Guest | Admin+ |
| `DELETE /folders/{id}/grants/{userId}` | → 204 | Admin+ |

### Documents (FR-5..9, FR-24)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /documents?workspace_id&folder_id&q&page` | → `Paginated<Document>`; `q` matches filename | any (scoped by access) |
| `POST /documents/upload-url` | `{ filename, mime_type, size_bytes, workspace_id, folder_id }` → `{ upload_url, storage_key, document_id }` | Member+ (or owner, personal) |
| `POST /documents/{id}/confirm-upload` | → `Document`; validates the uploaded object (FR-9) | as above |
| `GET /documents/{id}/download-url` | → `{ download_url, expires_in }` | anyone who can read it |
| `PATCH /documents/{id}` | `{ filename }` or `{ folder_id }` → `Document` | Member+ |
| `DELETE /documents/{id}` | → 204 (soft delete, FR-7) | Member+ |

**Upload flow (FR-5/6):** the client asks for a pre-signed URL, `PUT`s the bytes straight to object storage, then confirms. The `PUT` must send exactly the `Content-Type` it declared as `mime_type` (the URL is signed for it); a file with no MIME type is declared and sent as `application/octet-stream`. File bytes never pass through the API. `size_bytes` is checked against `MAX_UPLOAD_MB` (default 100); the client reads the same limit from `VITE_MAX_UPLOAD_MB`.

`Document.mime_type` and `size_bytes` describe the document's latest version (the highest `version_number`); `visibility` is derived (`private`, `workspace`, or `public` when an active share link exists); `deleted_at` is `null` for live documents.

### Share links (FR-10..15)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /documents/{id}/share-links` | → `ShareLink[]` **without `url`** | Member+ |
| `POST /documents/{id}/share-links` | `{ allow_download, password?, expires_at? }` → `ShareLink` **with `url`** | Member+ (never Guest) |
| `DELETE /share-links/{id}` | → 204; revocation is checked on every access (FR-13) | Member+ |

The server stores only a SHA-256 hash of the link token, so the `url` exists in exactly one response: the one that creates the link. It cannot be shown again; to get a new address, revoke the link and create another.

### Activity (FR-29, FR-30)

| Method & path | Response | Role |
|---|---|---|
| `GET /workspaces/{id}/activity?page` | → `Paginated<ActivityLogEntry>` | Admin+ |

## Not covered here

The public share-link endpoints (opening a link without an account, FR-11 and FR-15), email verification and password reset, and document versions/restore are not part of this client yet.
