---
description: Implement a functional requirement end-to-end using test-first workflow
argument-hint: <FR number, e.g. FR-17>
---

Implement $ARGUMENTS following the approved plan (run `/plan-fr $ARGUMENTS` first if none exists).

1. Confirm you're on a feature branch off `dev`, not `main`/`dev`.
2. Write failing tests first (happy path + authz denial + edge cases from the FR).
3. Implement the minimum to pass, respecting CLAUDE.md rules (authz only in `deps.py`, migrations via Alembic, storage via `StorageBackend`).
4. Run tests, `ruff check`, `mypy` / frontend lint + `tsc`. Fix until green; report real output.
5. Delegate to the `authz-reviewer` subagent if any route was added or changed.
6. Summarize what changed and anything deviating from the PRD. Do not commit unless asked.
