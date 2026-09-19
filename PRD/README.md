# DocVault — Documentation Index

This folder splits the DocVault specification into focused files, one per concern, so an editor, an AI coding assistant, or a human can pull in just the context relevant to the file they're working on instead of loading one large document.

| File | Use it when you're working on... |
|---|---|
| [01-project-objective.md](./01-project-objective.md) | Understanding *why* the product exists, before touching any code |
| [02-tech-stack.md](./02-tech-stack.md) | Setting up dependencies, `pyproject.toml` / `package.json`, choosing a library version |
| [03-architecture.md](./03-architecture.md) | Backend layering, request flow, where a new piece of logic belongs |
| [04-database-schema.md](./04-database-schema.md) | Models, migrations, anything touching PostgreSQL, tables, or relationships |
| [docvault-erd.drawio](./docvault-erd.drawio) | The editable ERD that backs file 04 |
| [05-role-model.md](./05-role-model.md) | Anything involving `workspace_members.role`, invites, ownership transfer |
| [06-permission-matrix.md](./06-permission-matrix.md) | Writing or reviewing an authorization check on any route |
| [07-functional-requirements.md](./07-functional-requirements.md) | Implementing a specific feature — find its FR number, implement exactly that |
| [08-deployment.md](./08-deployment.md) | `docker-compose.yml`, env vars, CI, or production config |
| [09-project-structure.md](./09-project-structure.md) | Deciding where a new file belongs in the repo |

**Suggested use in VS Code:** keep this `PRD/` folder at the repo root. When asking an AI assistant (Claude Code, Copilot Chat, etc.) to implement a feature, point it at the specific file(s) above rather than the whole spec — e.g. "implement FR-17 per `PRD/07-functional-requirements.md`, following the authorization pattern in `PRD/06-permission-matrix.md`."

