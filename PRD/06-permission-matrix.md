# 06 — Permission Model Matrix

| Action | Guest | Member | Admin | Owner |
|---|:---:|:---:|:---:|:---:|
| View documents in granted folders | ✅ | ✅ | ✅ | ✅ |
| Browse entire workspace | ❌ | ✅ | ✅ | ✅ |
| Upload / edit documents | ❌ | ✅ | ✅ | ✅ |
| Create folders | ❌ | ✅ | ✅ | ✅ |
| Create external share links | ❌ | ✅ (docs they can access) | ✅ | ✅ |
| See workspace member list | ❌ | ✅ | ✅ | ✅ |
| Invite members / guests | ❌ | ❌ | ✅ | ✅ |
| Grant/revoke guest folder access | ❌ | ❌ | ✅ | ✅ |
| Change member roles | ❌ | ❌ | ✅ (not Owner) | ✅ |
| Remove members | ❌ | ❌ | ✅ (not Owner) | ✅ |
| View activity/audit log | ❌ | ❌ | ✅ | ✅ |
| Manage workspace settings | ❌ | ❌ | ✅ | ✅ |
| Transfer ownership | ❌ | ❌ | ❌ | ✅ |
| Delete workspace | ❌ | ❌ | ❌ | ✅ |

Personal (non-workspace) documents sit outside this matrix entirely — access is just "are you the owner," independent of any workspace role.

## Implementation note (this is the security-critical part)

Every row above must be enforced by **one shared authorization dependency**, not re-implemented per route (see [03-architecture.md](./03-architecture.md) §"Application layer"). Concretely, for any request touching a `workspace_id`, `folder_id`, or `document_id`:

1. Resolve `current_user` from the JWT.
2. Look up `workspace_members` for `(workspace_id, current_user.id)`. No row → `403`/`404` (don't distinguish "doesn't exist" from "not authorized" in the response — that avoids leaking which workspaces exist).
3. If the row exists but the role is `guest`, additionally check `folder_grants` for the specific `folder_id` (or the document's `folder_id`) before allowing anything beyond this table's Guest row.
4. Compare the found role against this matrix for the specific action being attempted.

This is also exactly what the targeted test suite in [09-project-structure.md](./09-project-structure.md) (`test_cross_user_access.py`, etc.) should be exercising — one bug in this shared check is worse than a bug in any single route, so it deserves the most test attention.

Related: [05-role-model.md](./05-role-model.md) for what each role means, [04-database-schema.md](./04-database-schema.md) for the tables this reads from.
