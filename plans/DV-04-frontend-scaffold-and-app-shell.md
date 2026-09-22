# DV-04 — Frontend tooling, app shell, and API specification draft

**Status:** implemented and verified (branch `amol`, merged before this record was written; re-verified on 2026-09-22 from `share-link-activity-document-invites`).

## Goal
Stand up the real frontend toolchain (beyond the DV-02 skeleton) and build the app shell against the (at the time, not-yet-built) backend API: auth pages, workspace switching, a typed API client, and first-cut screens for documents, members/roles and share links, plus a draft API specification to align frontend and backend contracts.

## What was built
| Area | Result |
|---|---|
| Tooling | pnpm-only workspace (`pnpm-workspace.yaml`), ESLint config expanded, Prettier ignore rules, multi-stage frontend `Dockerfile`, Vite/TS config updates, `frontend/.env.example` |
| API client | `src/api/client.ts` (typed `apiFetch`, error shape handling) and per-resource modules: `auth.ts`, `workspaces.ts`, `folders.ts`, `documents.ts`, `members.ts`, `shareLinks.ts`, `activity.ts` |
| Auth | `auth/AuthContext.tsx`, `auth/ProtectedRoute.tsx` — session state, redirect-when-signed-out |
| Pages | `Login.tsx`, `Signup.tsx`, `WorkspaceSwitcher.tsx`, `Dashboard.tsx` (document list/upload/share entry points), `MembersRoles.tsx` |
| Components | `Sidebar.tsx`, `Modal.tsx`, `UploadModal.tsx`, `ShareLinkModal.tsx`, `InviteModal.tsx`, `RoleBadge.tsx`, `VisibilityBadge.tsx`, `ToastHost.tsx` |
| Cross-cutting | `permissions/roleHierarchy.ts` (client-side role gating, mirrors the backend permission matrix for UI hide/disable only), `workspace/WorkspaceContext.tsx`, `hooks/useToast.ts`, `hooks/useSafeAction.ts`, `hooks/useDebouncedValue.ts`, `types/index.ts` (mirrors backend Pydantic schemas), `styles/tokens.css` + `global.css` |
| Docs | `PRD/10-api-specification.md` created as a first draft (endpoints, error shape) from this frontend's needs; `frontend/README.md` written; upload size limit aligned to 100 MB across `.env.example` and `backend/app/config.py` |
| Tests | Vitest + RTL: `api/__tests__/client.test.ts`, `api/__tests__/documents.test.ts`, `auth/__tests__/ProtectedRoute.test.tsx`, `components/__tests__/ShareLinkModal.test.tsx`, `components/__tests__/Sidebar.test.tsx`, `hooks/__tests__/hooks.test.tsx`, `pages/__tests__/Login.test.tsx`, `pages/__tests__/MembersRoles.test.tsx`, `permissions/__tests__/roleHierarchy.test.ts` |

## Deviations from the original plan
- Built ahead of the backend routes it calls (auth, folders, documents, members, share links didn't exist yet — those landed in DV-05/DV-06/DV-07); `PRD/10-api-specification.md` was written here as the contract those later backend tasks implemented against, rather than the frontend consuming an already-specified API.
- None otherwise recorded beyond what's reflected in the current codebase, which later DV-05 through DV-09 work built on directly (same files, extended in place).

## Verification (real runs, re-confirmed 2026-09-22)
- Frontend: `pnpm lint` clean, `pnpm build` (`tsc -b && vite build`) clean — 80 modules transformed.
- `pnpm test` — 141 passed (22 files); this is the full current suite (later DV-06 through DV-09 work added tests on top of the DV-04 baseline rather than a standalone count for this task alone, since the same files were extended rather than replaced).

## Known gaps / notes
- This plan file was reconstructed retrospectively from the commit history and current repo state — DV-04 was implemented and merged before the project's "save a plan after verification" convention was in place for this repo. Content reflects the actual shipped state, not a forward-looking design.
- Client-side role gating (`roleHierarchy.ts`) is UI convenience only; the backend (`api/deps.py`) is the sole enforcement point, per the project's non-negotiable rules.

## Next
Backend API to match the drafted spec (DV-05, DV-06, DV-07), then the frontend wired to the real endpoints in place of whatever stubs/mocks this task shipped with.
