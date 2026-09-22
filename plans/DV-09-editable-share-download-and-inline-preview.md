# DV-09 — Editable share-link download toggle, and in-app document preview

**Status:** implemented and verified on 2026-09-22 (branch `share-link-activity-document-invites`, uncommitted).

## Goal
Two independent, user-requested additions:
1. Make a share link's "allow download" setting changeable after the link has already been created and handed out, without revoking it and losing the address.
2. Let anyone who can already see a document (Member/Admin/Owner, or a Guest with a grant) view it inline in the browser, not just download it — for the same content types the public share viewer already renders inline.

"Write/update" a document's content was explicitly **not** built here — the user confirmed that already means uploading a new version, which exists.

## What was built
| Area | Result |
|---|---|
| Share link download toggle | `PATCH /share-links/{id}` (`{ allow_download }`), Member+ (never Guest), same visibility rules as managing the link otherwise; the address (`url`) is never re-shown by this call. Logged as `share_link.updated` only when the value actually changes. `ShareLinkModal`'s "Allow download" toggle is now always enabled and applies immediately (no Save button, matching the app's existing instant-effect toggle pattern); the other two settings (password, expiry) stay creation-only |
| In-app preview | `GET /documents/{id}/preview-url` → `{ preview_url, expires_in }`, `Content-Disposition: inline`, same access rule as download (`get_document_access`); `415 NOT_PREVIEWABLE` for anything outside the previewable set. The previewable-type set (PDF, PNG, JPEG, GIF, WebP, plain text) moved out of `services/share_links.py` into a new shared `services/preview.py`, used by both the public share viewer and this endpoint. Dashboard gets a **View** button (gated client-side by `mime_type`, mirrored in `components/previewable.ts`) opening a new `PreviewModal` that renders the presigned URL in an `<iframe>`. The document's **filename itself is also clickable** for previewable types (same action as View, added on request) — plain, non-interactive text for anything else |
| Docs | PRD 10 (both new endpoints, `NOT_PREVIEWABLE` error code, `share_link.updated` activity action; also fixed two stale "folder grant" mentions left over from DV-08), frontend README |

## Deviations from the plan
- None — matches the clarified scope exactly (share-link toggle only; in-app inline preview; no editing).

## Verification (real runs)
- Backend: `ruff check`, `ruff format --check`, `mypy app` (strict, 65 files) clean. **452 tests: 446 pass, 6 skipped by default** (MinIO tests; 7/7 pass against real MinIO as before — unaffected by this change).
- **Mutation check:** 2 deliberate breakages (skip the `NOT_PREVIEWABLE` check, skip the `CREATE_SHARE_LINK` gate on the new PATCH route) were both caught by the tests.
- **Live end-to-end run:** the real API on the test database with real MinIO: 12 of 12 checks — preview-url for a PDF returns real bytes with `inline` disposition, a zip is refused with `415`, the share-link download toggle flips without changing the address, a re-opened link with download off still returns a working `preview_url` serving real bytes, and toggling back on restores `download_url`.
- Frontend: `lint`, `build` (`tsc`), `prettier` clean; **141 of 141 tests** (9 new: 2 for `PreviewModal`, 5 for the Dashboard `View` button and clickable-filename gating and behavior, 2 for the share-link toggle behavior).

## Known follow-ups
- No preview for Office formats (`.docx`/`.xlsx`/`.pptx`) or other types outside the small allowlist — download remains the only option for those, same as the public share viewer.
- The `PreviewModal` uses a plain `<iframe>`; there's no zoom/page controls beyond what the browser's own PDF/image viewer provides.

## To apply
No migration, no schema change. `docker compose up -d --build --no-deps api frontend` picks up both endpoints and the UI changes.
