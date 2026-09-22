# 05 — Role Model

Roles are scoped **per workspace** — a user's role is local to each workspace they belong to, not a global account attribute. Backed by `workspace_members.role` (see [04-database-schema.md](./04-database-schema.md)).

| Role | Description | Assigned via |
|---|---|---|
| **Owner** | Ultimate accountability for the workspace — usually its creator | Automatically on workspace creation; transferable to an existing Admin, never zero |
| **Admin** | Manages members, roles (below Owner), and workspace-wide structure | Invited directly as Admin, or promoted by an existing Admin/Owner |
| **Member** | Regular team user — uploads, organizes, shares what they can access | Default role on invite acceptance |
| **Guest** | External or limited collaborator restricted to specific granted documents | Invited as Guest, scoped via `document_grants` |

## Why four roles, not two, and not a generic permissions system

This set matches the actual decisions the product needs to make (who's accountable, who administers, who's a full member, who's a scoped-in outsider) without building a general-purpose permissions matrix the requirements don't call for yet. The schema is additive-friendly if that changes later — custom roles and per-resource ACLs beyond the Guest document grant stay a deliberate non-goal for v1 (see [01-project-objective.md](./01-project-objective.md) "Non-goals for v1").

## Lifecycle rules an implementation must enforce

- A workspace always has exactly one `owner`. Removing or demoting the sole Owner must be blocked until ownership is transferred to another existing member (promote them to Owner as part of the same transaction that demotes the current one).
- Role changes and ownership transfers are Admin/Owner-only actions (Owner-only for the transfer itself) — see the exact matrix in [06-permission-matrix.md](./06-permission-matrix.md).
- Removing a member or revoking a Guest's `document_grants` row must take effect immediately on the next request — there is no separate "propagate revocation" step, because access is derived live from these rows on every check.

Related: [06-permission-matrix.md](./06-permission-matrix.md) for exactly what each role can do, [07-functional-requirements.md](./07-functional-requirements.md) §"Workspaces & Membership" for the FRs this maps to.
