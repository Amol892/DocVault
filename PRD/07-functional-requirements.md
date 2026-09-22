# 07 — Functional Requirements

Each FR is independently implementable and testable. When asking an AI coding assistant to build a feature, reference it by number (e.g. "implement FR-17").

## Authentication & Accounts
- **FR-1**: Register with email + password; verify email before full access.
- **FR-2**: Passwords hashed with Argon2 (via `passlib`), never stored or logged in plaintext.
- **FR-3**: JWT-based auth on every protected route; short-lived access tokens.
- **FR-4**: Password reset flow via emailed, single-use, expiring token.

## Personal Document Storage
- **FR-5**: Upload a document (configurable size cap, default 100 MB) to a personal (non-workspace) space.
- **FR-6**: Files stored in MinIO/S3 addressed by an internal storage key — never a client-supplied path.
- **FR-7**: Owner can rename, move, download, or soft-delete their own documents; soft-deleted documents are recoverable within a grace period.
- **FR-8**: Re-uploading creates a new version (`document_versions`), not a silent overwrite.
- **FR-9**: Basic MIME-type/content validation on upload before a file becomes shareable.

## External Sharing via Link
- **FR-10**: Generate a share link for a single document, with a cryptographically random (≥128-bit) token.
- **FR-11**: No account required to open a share link.
- **FR-12**: Optional per-link password, expiry date, and allow/deny download.
- **FR-13**: Owner/editor can revoke a link at any time; revocation is checked on every access, not cached.
- **FR-14**: Link access is logged (timestamp, IP) and viewable by the document's owner.
- **FR-15**: The public share endpoint returns only the one document's data — never folder contents or other workspace metadata.

## Workspaces & Membership
- **FR-16**: Any authenticated user can create a workspace and becomes its Owner.
- **FR-17**: `GET /workspaces` returns only workspaces where the current user has a `workspace_members` row (owner/admin/member/guest) — nothing else is visible or discoverable.
- **FR-18**: Admins/Owners invite by email with a chosen role; invitees without an account sign up first, then accept.
- **FR-19**: Removing a member immediately revokes their access to all workspace documents and folders.
- **FR-20**: A workspace always has exactly one Owner; last-Owner removal/demotion is blocked until ownership is transferred.
- **FR-21**: Guests are invited scoped to specific *documents* (`document_grants`) and see only those documents, in a flat list — they have no standing on folders at all. A grant is folder-pinned: moving a granted document to a different folder revokes it.

## Folders & Organization
- **FR-22**: Create/rename/move/delete folders, nested via `parent_folder_id`.
- **FR-23**: Deleting a folder relocates or flags its documents rather than deleting them.
- **FR-24**: Search/filter documents by filename, uploader, or folder.

## API + Web UI
- **FR-25**: FastAPI REST API covering auth, workspaces, members, folders, documents, share-links, activity log — OpenAPI docs enabled in dev.
- **FR-26**: React + TypeScript UI: login/signup, workspace switcher (role shown per workspace), folder browser, upload flow, member/role management, share dialog.
- **FR-27**: The UI visually distinguishes "private to me," "shared within workspace," and "shared publicly via link" on every document.
- **FR-28**: `docker-compose up` brings up the full stack — API, Postgres, MinIO, frontend — including running pending Alembic migrations automatically.

## Auditability
- **FR-29**: Role changes, membership changes, ownership transfers, and guest folder-grant changes are recorded in `activity_logs`.
- **FR-30**: Admins/Owners can view a workspace's activity feed.

Related: [04-database-schema.md](./04-database-schema.md) for the tables each FR touches, [06-permission-matrix.md](./06-permission-matrix.md) for the authorization every route in this list must go through, [09-project-structure.md](./09-project-structure.md) for where each feature's code should live.
