---
paths:
  - "backend/**"
---

# Backend rules

- Layering: route (thin) → dependency in `api/deps.py` (authn + authz) → SQLAlchemy models. Business logic that outgrows a route goes in a service module, not in the route.
- All DB access is async (`AsyncSession`); no sync calls in request handlers.
- Every query on workspace-scoped data filters by `workspace_id`. Postgres RLS is a backstop, not a replacement.
- Deletion is soft where the PRD says so (see `PRD/07-functional-requirements.md`); check the FR before writing `DELETE`.
- Errors: raise `HTTPException` with a stable detail; return 404 (not 403) when the caller must not learn a resource exists.
- Passwords: argon2 via passlib. JWT handling only in `core/security.py`.
- Tests: pytest + httpx `AsyncClient`, real Postgres/MinIO for authz-critical tests (see `PRD/08-deployment.md`). Test files are named by risk area, not by route.
