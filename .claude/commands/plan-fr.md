---
description: Produce an implementation plan for a functional requirement (no code yet)
argument-hint: <FR number, e.g. FR-17>
---

Plan the implementation of $ARGUMENTS. Do NOT write code.

1. Read that FR in `PRD/07-functional-requirements.md`, plus only the PRD files it touches (04 schema, 05/06 roles & permissions, 09 structure).
2. Inspect the current code for what already exists.
3. Output a plan with: files to create/modify (per `PRD/09-project-structure.md`), migration needed (y/n), authz rule applied, API contract (method, path, request/response schemas), tests to write (including cross-user denial), and open questions or PRD ambiguities.
4. Stop and wait for approval.
