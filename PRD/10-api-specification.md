# 10 — API Specification (frontend contract)

> **Status.** Every endpoint below is **implemented** (`backend/app/api/routes/`) and covered by tests. A change to the API updates this file, the client (`frontend/src/api/`) and the types (`frontend/src/types/index.ts`) in the same change. Interactive docs: `/docs` on a running API.

## Conventions

- **Base path:** `/api/v1`. In development the Vite server proxies `/api` to the API, so the backend must mount its routers under `/api/v1` (or the proxy must rewrite).
- **Auth:** `Authorization: Bearer <JWT>` on every request except `POST /auth/register` and `POST /auth/login` (and the public share endpoints, later). Access tokens are JWTs (HS256) that live **24 hours** (`JWT_EXPIRE_MINUTES`, default 1440). There is **no refresh flow**: expiry means signing in again. Every token has a unique `jti`; `POST /auth/logout` **revokes** it server-side (blacklist), so a leaked token can be killed before it expires. A `401` on an authenticated request means the session is gone; the client drops it and returns to the login page.
- **Ids** are opaque 12-character strings (`RandomIdMixin`). Never assume a format, order or UUID.
- **Errors:** every non-2xx response, including validation errors and unknown routes, is `{ "error": { "code": "<STABLE_CODE>", "message": "<safe to show a user>" } }`. `message` never echoes request values (a rejected password is not repeated back) and never leaks whether a resource the caller cannot access exists: use `404` for both "missing" and "not yours" (PRD 06). Codes: `UNAUTHORIZED` (401, one message for a missing, malformed, expired, revoked or deactivated token), `BAD_CREDENTIALS` (401), `FORBIDDEN` (403), `CANNOT_MODIFY_OWNER` (403), `NOT_FOUND` (404), `EMAIL_NOT_VERIFIED` (403, the account's email is not confirmed yet), `INVALID_TOKEN` (400, an emailed link is invalid, used or expired), `EMAIL_TAKEN` (409), `TARGET_MUST_BE_ADMIN` (409), `ALREADY_MEMBER` (409), `INVITE_PENDING` (409), `INVITE_EMAIL_MISMATCH` (403), `INVITE_EXPIRED` / `INVITE_REVOKED` / `INVITE_USED` (410), `LINK_EXPIRED` / `LINK_REVOKED` (410, share links), `BAD_PASSWORD` (403, share link), `TOO_MANY_ATTEMPTS` (429, share link), `TOO_MANY_REQUESTS` (429), `FOLDER_CYCLE` (422), `NAME_TAKEN` (409, a live sibling folder has this name, ignoring case), `NOT_A_GUEST` (409, document grants are for Guests only), `UPLOAD_NOT_FOUND` (409, nothing was uploaded to confirm), `FILE_TOO_LARGE` (413), `NOT_PREVIEWABLE` (415), `FOLDER_TOO_DEEP` (422, nesting is capped at 20 levels), `UPLOAD_REJECTED` (422, the stored file failed validation; `message` says why), `VALIDATION_ERROR` (422), `METHOD_NOT_ALLOWED` (405), `INTERNAL_ERROR` (500).
- **Authorization** is enforced by the server on every call (`api/deps.py`, PRD 06). The "Role" column below is the minimum role; the client hides controls accordingly but is never the enforcement point.
- **Pagination:** `Paginated<T> = { items: T[], page: number, total: number }`, `page` starts at 1.
- **Timestamps** are ISO 8601 UTC strings.

## Endpoints

### Auth (FR-1..4)

| Method & path | Body → Response | Role |
|---|---|---|
| `POST /auth/register` | `{ email, password (8-128 chars), name }` → 201 `User` (`email_verified` is false until the emailed link is opened, unless `REQUIRE_EMAIL_VERIFICATION=false`). Emails are stored lower-cased; a duplicate (any case) is `409 EMAIL_TAKEN` | public |
| `POST /auth/login` | `{ email, password }` → `{ token, user: User }`. A wrong password, an unknown email and a deactivated account give the identical `401 BAD_CREDENTIALS` | public |
| `POST /auth/logout` | → 204. Revokes the token used for the call; afterwards that token gets `401` on every endpoint, and calling logout again with it is also `401`. The user's other tokens (other devices) stay valid | signed in |
| `GET /auth/me` | → `User` (includes `email_verified`) | any signed-in user, verified or not |
| `POST /auth/verify-email` | `{ token }` → 204. The token comes from the emailed link (`/verify-email/<token>`); it works once and expires after 24 h (`400 INVALID_TOKEN` otherwise) | public |
| `POST /auth/resend-verification` | → 204. Replaces the earlier link; a second request within a minute is `429`. A verified account is a no-op | signed in, verified or not |
| `POST /auth/forgot-password` | `{ email }` → 204 **always**, whether or not the address has an account (no enumeration). Sends a reset link (`/reset-password/<token>`) only to a real, active account, at most once a minute | public |
| `POST /auth/reset-password` | `{ token, password (8-128 chars) }` → 204. The link works once and expires after 60 min; a new request kills the earlier link. A successful reset also confirms the email | public |

**Email verification (FR-1).** Until an account's email is confirmed, every endpoint except `/auth/me`, `/auth/logout`, `/auth/resend-verification` and the public ones answers `403 EMAIL_NOT_VERIFIED`; the UI shows a "confirm your email" screen with a resend button. Accounts that existed before verification was added count as verified. Tokens are 256 random bits; only their SHA-256 hash is stored (`auth_tokens`), and a token is consumed by one conditional `UPDATE`, so two requests can never both use it. Not built: revoking a user's other sessions when the password changes.

Revocation is stored in `revoked_tokens` (the token's `jti`, its owner and its own expiry). Rows are deleted once the token would have expired anyway. "Log out everywhere" (revoke all of a user's tokens) and revoking on password change are not built yet.

### Workspaces and members (FR-16..21)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /workspaces` | → `WorkspaceSummary[]` (only workspaces the caller belongs to, FR-17) | any |
| `POST /workspaces` | `{ name }` → 201 `Workspace`; the caller becomes Owner | any |
| `GET /workspaces/{id}` | → `Workspace`, which includes **`my_role`** (the caller's own role: Guests cannot list members, so this is how every role learns theirs). `404` for a missing, deleted or not-yours workspace alike | member of it |
| `DELETE /workspaces/{id}` | → 204. A **soft delete**: it then behaves as missing for everyone | Owner |
| `GET /workspaces/{id}/members` | → `WorkspaceMember[]` (guests include `granted_document_ids`) | Member+ |
| `PATCH /workspaces/{id}/members/{userId}` | `{ role: "admin" or "member" or "guest" }` → 204. `owner` is rejected (422): ownership only moves by transfer. Leaving `guest` clears the user's document grants | Admin+ (never the Owner row: `403 CANNOT_MODIFY_OWNER`) |
| `DELETE /workspaces/{id}/members/{userId}` | → 204; access is revoked immediately (FR-19) | Admin+ (never the Owner row) |
| `POST /workspaces/{id}/members/{userId}/transfer-ownership` | → 204. The target must be an existing **Admin** (`409 TARGET_MUST_BE_ADMIN`); the Owner becomes an Admin in the same transaction, so there is always exactly one Owner | Owner |
| `POST /workspaces/{id}/invites` | `{ email, role: "admin"\|"member"\|"guest", document_ids? }` → 201 `WorkspaceInvite`. Emails the invitation **and** returns its `url` once (with `email_sent`), so an admin can hand it over if the email does not arrive. `document_ids` (Guest only) are granted on acceptance (FR-21). `409 ALREADY_MEMBER` / `409 INVITE_PENDING`; an expired pending invite is replaced. Expires after 7 days (`INVITE_EXPIRE_DAYS`) | Admin+ |
| `GET /workspaces/{id}/invites` | → `WorkspaceInvite[]` still waiting (never includes `url`) | Admin+ |
| `DELETE /workspaces/{id}/invites/{inviteId}` | → 204; the link stops working at once | Admin+ |
| `GET /invites/{token}` | → `{ workspace_name, role, email, expired }`; `404` unknown, `410` revoked / expired / used | public (the token is the credential) |
| `POST /invites/{token}/accept` | → 204. Only the account **whose email was invited** can accept (`403 INVITE_EMAIL_MISMATCH`); joins with the invited role and, for a Guest, the invited document grants. Accepting twice is harmless; an invitation used by someone who was later removed is `410 INVITE_USED` | signed in, verified |

A workspace always has exactly one Owner (FR-20); `role: "owner"` is never accepted by an invite or a role change.

### Folders (FR-21..23)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /workspaces/{id}/folders` | → `Folder[]`; always `[]` for a Guest — a Guest has no standing on any folder at all (FR-21) | Member+ |
| `POST /workspaces/{id}/folders` | `{ name, parent_folder_id }` → `Folder` | Member+ |
| `PATCH /folders/{id}` | exactly one of `{ name }` (rename) or `{ parent_folder_id }` (move with everything in it; `null` = the workspace root) → `Folder`. `422 FOLDER_CYCLE` into itself or a descendant, `422 FOLDER_TOO_DEEP` if the moved tree would exceed 20 levels, `409 NAME_TAKEN` on a sibling clash, `404` for a target in another workspace or for a Guest (no standing on any folder) | Member+ |
| `DELETE /folders/{id}` | → 204; soft delete. Sub-folders and documents move up to the deleted folder's parent (or the root), renamed `name (moved 2)` on a name clash; Guest grants on documents that move this way are revoked, since grants are folder-pinned (FR-23) | Member+ |

A Guest is never a member of any folder request: `GET .../folders` returns `[]` for them and every other folder endpoint answers `404`, the same as a folder that does not exist. See Documents below for how a Guest is actually given access.

### Documents (FR-5..9, FR-24)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /documents?workspace_id&folder_id&q&page` | → `Paginated<Document>` (page size 50, newest first); without `workspace_id` it lists the caller's personal documents; `q` matches filename or uploader name (case-insensitive substring). Only documents with a confirmed file are listed. For a **Guest**, `folder_id` is ignored — they always get their flat set of individually granted documents (FR-21), never a folder-scoped view | any (scoped by access) |
| `POST /documents/upload-url` | `{ filename, mime_type, size_bytes, workspace_id, folder_id, document_id? }` → `{ upload_url, storage_key, document_id }`; send `document_id` to add a **new version** to an existing document (the other fields are then ignored) | Member+ (or owner, personal) |
| `POST /documents/{id}/confirm-upload` | → `Document`; validates the uploaded object (FR-9), idempotent | as above |
| `GET /documents/{id}/download-url` | → `{ download_url, expires_in }` | anyone who can read it |
| `GET /documents/{id}/preview-url` | → `{ preview_url, expires_in }` (`Content-Disposition: inline`). Only for the previewable types (PDF, PNG, JPEG, GIF, WebP, plain text) — `415 NOT_PREVIEWABLE` otherwise | anyone who can read it |
| `PATCH /documents/{id}` | exactly one of `{ filename }` or `{ folder_id }` (`null` = the workspace root) → `Document`. Changing `folder_id` revokes any Guest grants on the document (folder-pinned, FR-21) | Member+ |
| `DELETE /documents/{id}` | → 204 (soft delete, FR-7) | Member+ |
| `POST /documents/{id}/grants` | `{ user_id }` → 204, idempotent; the user must be a member (404) and a Guest (`NOT_A_GUEST`); logged as `guest.document_granted` (FR-21) | Admin+ |
| `DELETE /documents/{id}/grants/{userId}` | → 204, idempotent, effective on the next request; logged as `guest.document_revoked` | Admin+ |

**Guest access (FR-21):** a Guest has no standing on any folder — folders are entirely a Member-and-above concept. A Guest instead sees a flat list of exactly the documents individually granted to them. Grants are **folder-pinned**: moving a granted document (directly, or indirectly because the folder it was in was deleted and its contents re-parented, FR-23) revokes the grant; it must be re-granted afterward.

**Upload flow (FR-5/6):** the client asks for a pre-signed URL, `PUT`s the bytes straight to object storage, then confirms. The `PUT` must send exactly the `Content-Type` it declared as `mime_type` (the URL is signed for it); a file with no MIME type is declared and sent as `application/octet-stream`. File bytes never pass through the API. `size_bytes` is checked against `MAX_UPLOAD_MB` (default 100); the client reads the same limit from `VITE_MAX_UPLOAD_MB` (over the limit: `413 FILE_TOO_LARGE`).

The server picks the storage key (`w/<workspace>/<document>/<version>` or `u/<user>/<document>/<version>`); it is never derived from the filename. The upload URL lasts 15 minutes and is signed for the declared `Content-Type` and `Content-Length`; storage itself refuses a different type or size (403). It is signed for `S3_PUBLIC_ENDPOINT_URL` (the address the browser can reach), while the API talks to storage through `S3_ENDPOINT_URL`.

**Confirm (FR-9):** the API reads the object's size and content type from storage and its first 512 bytes, and refuses the upload (`422 UPLOAD_REJECTED`, object deleted, version marked rejected) if the size or content type differs from what was declared, if the file is an executable (Windows PE, ELF, Mach-O, shebang script, whatever it claims to be), or if a PDF / image / Office / ZIP type does not start with the matching magic bytes. A document whose only upload was rejected disappears. This is basic validation, not antivirus.

**Versions (FR-8):** every upload adds a version; the *current* version is the highest-numbered confirmed one, so a re-upload that is still pending or was rejected never hides the previous file. Download URLs (`expires_in` 300 s) force `Content-Disposition: attachment`.

`Document.mime_type` and `size_bytes` describe the document's latest version (the highest `version_number`); `visibility` is derived (`public` when an active, unexpired, unrevoked share link exists, otherwise `private` for a personal document and `workspace` for a workspace one); `deleted_at` is `null` for live documents.

**Trash, restore and versions:**

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /documents/trash?workspace_id&page` | → `Paginated<Document>`: recently deleted documents still restorable (FR-7); without `workspace_id`, the caller's own personal documents. `403` for Guests | Member+ / owner |
| `POST /documents/{id}/restore` | → `Document`. Within the grace period (`TRASH_GRACE_DAYS`, default 30); if its folder was deleted meanwhile it returns to the workspace root. `404` for anything not in the caller's trash | Member+ / owner |
| `GET /documents/{id}/versions` | → `DocumentVersion[]` (confirmed versions, newest first, `is_current` on the first) (FR-8) | anyone who can read it |
| `GET /documents/{id}/versions/{n}/download-url` | → `{ download_url, expires_in }` for that version | anyone who can read it |

**Purge (FR-7).** The `purge` service (`python -m app.jobs.purge --every 3600`) removes documents deleted longer than the grace period ago (objects, versions, share links and their logs), abandons uploads never confirmed within `PENDING_UPLOAD_TTL_HOURS` (24) and deletes expired `revoked_tokens`. It is idempotent and safe to run at any time.

### Share links (FR-10..15)

| Method & path | Body → Response | Role |
|---|---|---|
| `GET /documents/{id}/share-links` | → `ShareLink[]` **without `url`** (`expired` is derived from `expires_at`) | Member+ |
| `POST /documents/{id}/share-links` | `{ allow_download (default true), password? (4-128 chars), expires_at? (future) }` → 201 `ShareLink` **with `url`** (`<FRONTEND_URL>/s/<token>`) | Member+ (never Guest); the owner of a personal document |
| `PATCH /share-links/{id}` | `{ allow_download }` → `ShareLink` **without `url`**. The only setting changeable after creation — the address stays the same; the password and expiry are fixed for the life of the link (revoke and create a new one to change those) | Member+ (never Guest) |
| `DELETE /share-links/{id}` | → 204, idempotent; revocation is checked on every access (FR-13) | Member+ |
| `GET /share-links/{id}/access-log?page` | → `Paginated<{ accessed_at, ip_address, user_agent, outcome }>`, newest first (FR-14) | whoever may manage the link |
| `POST /public/share/{token}/access` | `{ password? }` → `{ requires_password, filename, mime_type, size_bytes, allow_download, expires_at, download_url, preview_url }` (FR-11, FR-15). No account. While a password is needed and not sent, only `requires_password: true` is returned. `404` unknown / deleted document / deleted workspace (all alike), `410 LINK_REVOKED` / `LINK_EXPIRED`, `403 BAD_PASSWORD`, `429 TOO_MANY_ATTEMPTS` (10 wrong passwords per link and client address in 15 min) | public |

The public response holds only that one document's details and 5-minute pre-signed URLs, never owner, folder or workspace details (the storage key inside a URL contains only opaque ids). `download_url` exists only when the link allows download. `preview_url` (`Content-Disposition: inline`) exists only for PDF, PNG, JPEG, GIF, WebP and plain text; every other type is only ever served as an attachment, so an uploaded HTML or SVG file can never run in the browser. A recipient who can preview can still save what they see: "no download" is a convenience, not DRM. Toggling `allow_download` off after a link is out does not break the address: the recipient keeps the same URL, and `download_url` simply stops being returned (`preview_url` is unaffected, if the type supports it). Every outcome (`ok`, `bad_password`, `expired`, `revoked`) is logged with IP and user agent. The client address is the socket peer; behind a reverse proxy the proxy must pass it on (not configured yet).

The server stores only a SHA-256 hash of the link token, so the `url` exists in exactly one response: the one that creates the link. It cannot be shown again; to get a new address, revoke the link and create another.

**Email (FR-1, FR-4, FR-18).** Every email DocVault sends (verify, reset, invite) is `multipart/alternative`: an HTML body from `backend/app/templates/emails/*.html` (rendered with Jinja2, autoescaped) plus a plain-text fallback for clients that don't render HTML. Without `SMTP_HOST` set, only the plain-text version is logged (`docker compose logs api`) — that's how a developer reads the links in local dev.

### Activity (FR-29, FR-30)

| Method & path | Response | Role |
|---|---|---|
| `GET /workspaces/{id}/activity?page` | → `Paginated<ActivityLogEntry>` (`{ id, actor_id, actor_name, action, target_type, target_id, metadata, created_at }`, page size 50, newest first) | Admin+ |

Actions recorded: `workspace.created`, `workspace.deleted`, `member.invited`, `member.joined`, `member.role_changed`, `member.removed`, `ownership.transferred`, `guest.document_granted`, `guest.document_revoked`, `invite.revoked`, `share_link.created`, `share_link.updated`, `share_link.revoked`.

## Not covered here

Refresh tokens, "log out everywhere" and revoking sessions on a password change, login rate limiting, and a local-disk storage backend.
