# 06 — Permission Model Matrix

| Action | Guest | Member | Admin | Owner |
|---|:---:|:---:|:---:|:---:|
| View individually granted documents | ✅ | ✅ | ✅ | ✅ |
| Browse entire workspace, including folders | ❌ | ✅ | ✅ | ✅ |
| Upload / edit documents | ❌ | ✅ | ✅ | ✅ |
| Create folders | ❌ | ✅ | ✅ | ✅ |
| Create external share links | ❌ | ✅ (docs they can access) | ✅ | ✅ |
| See workspace member list | ❌ | ✅ | ✅ | ✅ |
| Invite members / guests | ❌ | ❌ | ✅ | ✅ |
| Grant/revoke guest document access | ❌ | ❌ | ✅ | ✅ |
| Change member roles | ❌ | ❌ | ✅ (not Owner) | ✅ |
| Remove members | ❌ | ❌ | ✅ (not Owner) | ✅ |
| View activity/audit log | ❌ | ❌ | ✅ | ✅ |
| Manage workspace settings | ❌ | ❌ | ✅ | ✅ |
| Transfer ownership | ❌ | ❌ | ❌ | ✅ |
| Delete workspace | ❌ | ❌ | ❌ | ✅ |

Personal (non-workspace) documents sit outside this matrix entirely — access is just "are you the owner," independent of any workspace role.

A Guest's access is **per document**, not per folder (FR-21): a Guest has no standing on any folder at all — `GET .../folders` always returns an empty list for them, and every folder-scoped endpoint answers `404` for a Guest regardless of what is granted, the same as for a folder that does not exist. Grants are folder-pinned: they name a document, but moving that document to a different folder (directly, or indirectly when the folder it was in is deleted and its contents re-parented, FR-23) revokes the grant, since the guarantee "this address only shows what was explicitly handed over" would otherwise erode as things get reorganized.

## Implementation note (this is the security-critical part)

Every row above must be enforced by **one shared authorization dependency**, not re-implemented per route (see [03-architecture.md](./03-architecture.md) §"Application layer"). Concretely, for any request touching a `workspace_id`, `folder_id`, or `document_id`:

1. Resolve `current_user` from the JWT.
2. Look up `workspace_members` for `(workspace_id, current_user.id)`. No row → `403`/`404` (don't distinguish "doesn't exist" from "not authorized" in the response — that avoids leaking which workspaces exist).
3. For a `folder_id`: if the role is `guest`, the request is always `404` — Guests never have folder standing.
4. For a `document_id`: if the role is `guest`, additionally check `document_grants` for that specific document before allowing anything beyond the Guest row above.
5. Compare the found role against this matrix for the specific action being attempted.

This is also exactly what the targeted test suite in [09-project-structure.md](./09-project-structure.md) (`test_cross_user_access.py`, etc.) should be exercising — one bug in this shared check is worse than a bug in any single route, so it deserves the most test attention.
