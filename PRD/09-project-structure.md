# 09 — Project Structure

```
docvault/
├── docker-compose.yml
├── docker-compose.override.yml.example
├── .env.example
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_init_schema.py
│   ├── app/
│   │   ├── main.py                  # FastAPI app instantiation
│   │   ├── config.py                # env-driven settings (pydantic-settings)
│   │   ├── db/
│   │   │   ├── session.py           # async SQLAlchemy engine/session
│   │   │   └── base.py              # declarative base, model registry
│   │   ├── models/                  # SQLAlchemy models, one file per table group
│   │   │   ├── user.py
│   │   │   ├── workspace.py
│   │   │   ├── folder.py
│   │   │   ├── document.py
│   │   │   ├── share_link.py
│   │   │   └── activity.py
│   │   ├── schemas/                 # Pydantic request/response models
│   │   ├── api/
│   │   │   ├── deps.py              # auth + authorization dependencies (see 06-permission-matrix.md)
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── workspaces.py
│   │   │       ├── members.py
│   │   │       ├── folders.py
│   │   │       ├── documents.py
│   │   │       └── share_links.py
│   │   ├── storage/
│   │   │   ├── base.py              # StorageBackend protocol
│   │   │   ├── s3_backend.py        # MinIO/S3 implementation
│   │   │   └── local_backend.py     # local-disk implementation
│   │   └── core/
│   │       ├── security.py          # password hashing, JWT
│   │       └── logging.py
│   └── tests/
│       ├── test_cross_user_access.py
│       ├── test_share_link_scoping.py
│       ├── test_membership_removal.py
│       ├── test_deletion_semantics.py
│       └── test_storage_backends.py
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/                     # typed API client
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── WorkspaceSwitcher.tsx
│   │   │   ├── FolderBrowser.tsx
│   │   │   ├── DocumentDetail.tsx
│   │   │   └── MemberManagement.tsx
│   │   ├── components/
│   │   └── types/
│   └── tests/
│
└── docs/                            # this folder — 01 through 09, plus the ERD
    ├── 01-project-objective.md
    ├── 02-tech-stack.md
    ├── 03-architecture.md
    ├── 04-database-schema.md
    ├── 05-role-model.md
    ├── 06-permission-matrix.md
    ├── 07-functional-requirements.md
    ├── 08-deployment.md
    ├── 09-project-structure.md
    ├── api-specification.md
    └── docvault-erd.drawio
```

## Structure notes

- In this repo the specs live in `PRD/` (not `docs/`): `PRD/docvault-erd.drawio` sits beside `PRD/04-database-schema.md`. Every model inherits `RandomIdMixin` and `TimestampMixin` from `backend/app/db/base.py` (see 04).
- `backend/app/api/deps.py` is deliberately the single place authorization logic lives — matches [03-architecture.md](./03-architecture.md)'s note that this must not be duplicated per-route, and is exactly what [06-permission-matrix.md](./06-permission-matrix.md) describes checking.
- `backend/app/storage/` holds the `StorageBackend` interface and both implementations side by side, so the abstraction described in [02-tech-stack.md](./02-tech-stack.md) / [08-deployment.md](./08-deployment.md) is visible in the file layout, not just in prose.
- `backend/tests/` file names map directly to the risk areas called out in [06-permission-matrix.md](./06-permission-matrix.md) (cross-user access, share-link scoping, membership removal, deletion semantics) rather than being organized by route — find "the test that would catch this" by risk area, not by inferring it from generic route-based test files.
- Every FR in [07-functional-requirements.md](./07-functional-requirements.md) maps to one or more files under `backend/app/api/routes/` and, where relevant, `frontend/src/pages/` — when implementing an FR, that's where the code belongs.
