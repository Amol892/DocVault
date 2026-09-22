# DocVault Frontend

React + TypeScript single-page app for DocVault: sign in, switch between workspaces, browse and upload documents, share them by link, and manage members and roles.

It is written against the API described in [PRD/10-api-specification.md](../PRD/10-api-specification.md). The backend implements every endpoint in that document, so every screen loads real data. There is no mock mode.

## Stack

React 19.2, TypeScript 5.7 (strict), Vite 6, React Router 6, Vitest + React Testing Library, ESLint 9, Prettier. Versions are pinned exactly and match [PRD/02-tech-stack.md](../PRD/02-tech-stack.md). State is plain React context plus `fetch`; no state library or UI kit.

## Run it

Requires Node 22+ and pnpm 12 (`corepack enable` or `npm i -g pnpm@12.4.2`).

```bash
pnpm install
pnpm dev            # http://localhost:5173, proxies /api to http://localhost:8000
```

With the whole stack: `docker compose up --build` from the repo root serves the dev server on http://localhost:5173 and proxies `/api` to the `api` container.

| Setting              | Where                                                     | Default                 |
| -------------------- | --------------------------------------------------------- | ----------------------- |
| `VITE_API_BASE_URL`  | `frontend/.env`                                           | `/api/v1`               |
| `VITE_MAX_UPLOAD_MB` | `frontend/.env` (keep equal to the API's `MAX_UPLOAD_MB`) | `100`                   |
| `API_PROXY_TARGET`   | environment, read by `vite.config.ts`                     | `http://localhost:8000` |

## Scripts

```bash
pnpm lint           # ESLint (also runs in CI)
pnpm format         # Prettier; `pnpm format:check` only verifies
pnpm test           # Vitest, run once; `pnpm test:watch` to iterate
pnpm build          # tsc -b (type-check) then a production build in dist/
```

The Dockerfile has two targets: `dev` (Vite dev server with the `/api` proxy, used by Compose) and `prod` (static build served on :4173; put a reverse proxy in front for `/api` and TLS).

## Layout

```
src/
  api/          typed API client (client.ts) and one module per resource
  auth/         AuthContext, ProtectedRoute
  workspace/    WorkspaceContext (workspace, members, current user's role)
  permissions/  role hierarchy and action checks (UX only)
  pages/        Login, Signup, WorkspaceSwitcher, Dashboard, MembersRoles
  components/   Sidebar, Modal, Upload/Invite/ShareLink modals, badges, toasts
  hooks/        useToast, useSafeAction, useDebouncedValue
  types/        API types (mirror the API spec and the database schema)
  config.ts     build-time settings
```

## How it behaves

- **Signing out revokes the token on the server** (`POST /auth/logout`), not just in the browser, so a copied token stops working immediately. The local session is cleared even if that call fails.
- **The user's role comes from the workspace** (`my_role`), not from the member list, because Guests are not allowed to list members.
- **Every API call goes through `src/api/client.ts`.** It attaches the token, turns error responses into `ApiClientError`, and on a `401` for a signed-in user drops the session and returns to the login page. Components never call `fetch` themselves.
- **Failures are shown, not swallowed.** UI actions run through `useSafeAction`, which turns any error into a toast; pages that load data show an error state instead of an empty one.
- **Uploads use a pre-signed URL:** request the URL, `PUT` the bytes straight to storage with the same `Content-Type` that was declared, then confirm. File bytes never pass through the API.
- **Share-link addresses appear once.** The server stores only a hash of the token, so a link's URL is shown right after it is created and can never be shown again. To get a new address, revoke the link and create another.
- **Roles.** `permissions/roleHierarchy.ts` mirrors the permission matrix ([PRD/06](../PRD/06-permission-matrix.md)) to hide or disable actions a user cannot take. **It is not a security control.** The server checks every request; a Member sees the member list read-only, a Guest sees only the documents individually granted to them, in a flat list — Guests have no standing on any folder at all (the API returns just what was granted; the UI does not filter).

## Security notes

- The session token is kept in `localStorage`, which any script running on the page can read. There is no XSS sink in the code (no `dangerouslySetInnerHTML`), tokens should be short-lived (FR-3), and moving to an `httpOnly` cookie with CSRF protection is a reasonable later hardening.
- Passwords are only ever sent to the API over HTTPS in production; nothing is logged.

## Tests

`pnpm test` runs 141 tests: the permission rules, the API client (headers, error mapping, session expiry) and its document module, the upload content-type rule, route protection (including the unconfirmed-email gate), login (with the `next` redirect) and the profile menu, the role-dependent members page with pending invitations, the sidebar's folder list with create / rename / move / delete, the dashboard's document actions (rename, move, delete, new version, version history, inline preview), the trash, the activity log, the share-link modal (including the editable download toggle) and the public share viewer, the invite modal and accept page, email verification and password reset, sign-out, and the workspace context. Vitest reads its settings from `vite.config.ts`; the jest-dom setup is `src/test/setup.ts`.

## Not built yet

- Profile editing (name, email, password change while signed in): the profile menu is read-only and the API has no endpoint for it.
- Personal documents (outside any workspace): the API supports them, the UI only shows workspaces.
- Moving several documents at once, and a folder tree view (the sidebar lists folders flat, indented by nesting).
- Restoring an old version as the current one (older versions can be downloaded).
