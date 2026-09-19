# 04 — Database Approach, Schema, Tables & Relationships

## Approach

- **Single shared PostgreSQL database**, not database-per-tenant or schema-per-tenant — the right trade-off at this scale (no banking/healthcare-grade regulatory driver), avoiding the operational cost of per-tenant migrations and provisioning.
- **`workspace_id` as the tenant-scoping column** on every workspace-owned table, filtered on every query at the application layer.
- **PostgreSQL Row-Level Security (RLS)** enabled on every workspace-owned table as a database-enforced backstop, so a bug or missing filter in application code fails closed instead of leaking another tenant's rows. The current user's ID is set via `SET LOCAL` at the start of each request's transaction; RLS policies read it via `current_setting(...)`.
- **All schema changes go through Alembic migrations** — no manual DDL against a running database, ever.
- **Soft deletion** for documents and folders (a `is_deleted`/`deleted_at` flag, not a hard `DELETE`), so accidental removal is recoverable within a grace period.

## Entity-relationship diagram

```mermaid
erDiagram
    USERS ||--o{ WORKSPACES : owns
    USERS ||--o{ WORKSPACE_MEMBERS : "is member via"
    WORKSPACES ||--o{ WORKSPACE_MEMBERS : has
    WORKSPACES ||--o{ WORKSPACE_INVITES : has
    WORKSPACES ||--o{ FOLDERS : contains
    WORKSPACES ||--o{ DOCUMENTS : contains
    WORKSPACES ||--o{ ACTIVITY_LOGS : logs
    USERS ||--o{ FOLDERS : "owns (personal)"
    USERS ||--o{ DOCUMENTS : owns
    FOLDERS ||--o{ FOLDERS : "parent of"
    FOLDERS ||--o{ DOCUMENTS : contains
    FOLDERS ||--o{ FOLDER_GRANTS : "grants access to"
    USERS ||--o{ FOLDER_GRANTS : "granted (guest)"
    DOCUMENTS ||--o{ DOCUMENT_VERSIONS : "has versions"
    DOCUMENTS ||--o{ SHARE_LINKS : "shared via"
    SHARE_LINKS ||--o{ SHARE_LINK_ACCESS_LOGS : "accessed via"

    USERS {
        uuid id PK
        citext email
        text password_hash
        text name
        bool email_verified
    }
    WORKSPACES {
        uuid id PK
        text name
        uuid owner_id FK
    }
    WORKSPACE_MEMBERS {
        uuid workspace_id PK_FK
        uuid user_id PK_FK
        enum role "owner|admin|member|guest"
    }
    WORKSPACE_INVITES {
        uuid id PK
        uuid workspace_id FK
        citext email
        enum role
        text token
        timestamptz expires_at
    }
    FOLDERS {
        uuid id PK
        uuid workspace_id FK "nullable = personal"
        uuid owner_id FK
        uuid parent_folder_id FK
        text name
    }
    FOLDER_GRANTS {
        uuid id PK
        uuid folder_id FK
        uuid user_id FK
        uuid granted_by FK
    }
    DOCUMENTS {
        uuid id PK
        uuid owner_id FK
        uuid workspace_id FK "nullable = personal"
        uuid folder_id FK
        text filename
        text storage_key
        uuid current_version_id FK
        bool is_deleted
    }
    DOCUMENT_VERSIONS {
        uuid id PK
        uuid document_id FK
        int version_number
        text storage_key
        uuid created_by FK
    }
    SHARE_LINKS {
        uuid id PK
        uuid document_id FK
        text token
        uuid created_by FK
        text password_hash
        timestamptz expires_at
        timestamptz revoked_at
    }
    SHARE_LINK_ACCESS_LOGS {
        uuid id PK
        uuid share_link_id FK
        timestamptz accessed_at
        inet ip_address
    }
    ACTIVITY_LOGS {
        uuid id PK
        uuid workspace_id FK
        uuid actor_id FK
        text action
        jsonb metadata
    }
```

## Table summary

| Table | Purpose | Notes on deletion / membership handling |
|---|---|---|
| `users` | Account identity, credentials | Never hard-deleted in v1 (deactivation flag preferred over removal, to preserve `owner_id`/`created_by` history) |
| `workspaces` | A tenant/team | Owner transfer required before an Owner can leave; deleting cascades to members/folders/documents (soft-delete recommended over hard cascade in production) |
| `workspace_members` | Who belongs to a workspace, and at what role | Composite PK `(workspace_id, user_id)`; row deletion = immediate access revocation |
| `workspace_invites` | Pending invitations | Unique partial index prevents duplicate pending invites to the same email; expires automatically |
| `folders` | Organizational hierarchy | `workspace_id NULL` = personal folder; deleting a folder relocates or flags its documents, never silently deletes them |
| `folder_grants` | Guest-role scoping to specific folders | Deleting the grant is the entire revocation mechanism for a Guest's access to that folder |
| `documents` | File metadata, one row per logical document | Soft-deleted (`is_deleted`/`deleted_at`); `current_version_id` always points at the active version |
| `document_versions` | Version history | Append-only; never deleted when a document gets a new version |
| `share_links` | External, token-based access to one document | Revocation is a flag (`revoked_at`), not a delete, so access logs remain attributable |
| `share_link_access_logs` | Audit trail for link usage | Append-only |
| `activity_logs` | Workspace-level audit trail | Append-only; `workspace_id` nullable only for platform-level events, if any exist later |

## Key relationship rules enforced by the schema

- A document's access path is exactly one of: **owned personally** (`workspace_id NULL`, `owner_id` = you) or **workspace-scoped** (`workspace_id` set, checked against `workspace_members`) — never both, never neither.
- `documents.current_version_id` is a forward reference into `document_versions`, added via `ALTER TABLE ... ADD CONSTRAINT` after both tables exist, since the two tables reference each other.
- A workspace must have exactly one `owner`-role row in `workspace_members` at all times (enforced via constraint/trigger, not just convention).

Related: [05-role-model.md](./05-role-model.md) for what `role` values mean, [06-permission-matrix.md](./06-permission-matrix.md) for how these tables get checked on every request, `docvault-erd.drawio` (in the repo's `docs/` or diagrams folder) for the visual ERD, `001_init_schema.sql` / the Alembic migration for the literal DDL.
