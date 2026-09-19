---
description: Create and review an Alembic migration for pending model changes
argument-hint: <short message>
---

1. Compare `backend/app/models/` against `PRD/04-database-schema.md`; flag mismatches.
2. Run `alembic revision --autogenerate -m "$ARGUMENTS"`.
3. Review the generated file: add missing indexes, RLS policies, enum handling; ensure `downgrade()` works.
4. Run `alembic upgrade head`, then `alembic downgrade -1`, then `upgrade head` against the dev DB to prove it round-trips.
5. Report the result.
