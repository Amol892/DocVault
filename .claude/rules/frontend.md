---
paths:
  - "frontend/**"
---

# Frontend rules

- React 19 function components + hooks only. TypeScript `strict`; no `any`.
- All HTTP goes through the typed client in `src/api/`; components never call `fetch` directly.
- Types mirror backend Pydantic schemas in `src/types/`. If the API changes, update the types in the same change.
- Uploads/downloads use the pre-signed URLs returned by the API; never embed storage credentials.
- UI must hide/disable actions the user's role can't perform, but the backend is the enforcement point — never rely on the UI for security.
- Tests: Vitest + React Testing Library; test behaviour, not implementation details.
