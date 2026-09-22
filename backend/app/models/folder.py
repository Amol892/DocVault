from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column


class Folder(RandomIdMixin, TimestampMixin, Base):
    """Folder hierarchy. workspace_id NULL means a personal folder owned by owner_id."""

    __tablename__ = "folders"
    __table_args__ = (
        CheckConstraint(r"length(name) BETWEEN 1 AND 255 AND name !~ '[/\\]'", name="name_valid"),
        Index("ix_folders_workspace_id_parent_folder_id", "workspace_id", "parent_folder_id"),
        Index(
            "ix_folders_personal_owner_id",
            "owner_id",
            postgresql_where=text("workspace_id IS NULL"),
        ),
    )

    workspace_id: Mapped[str | None] = fk_column("workspaces.id", nullable=True)
    owner_id: Mapped[str] = fk_column("users.id")
    parent_folder_id: Mapped[str | None] = fk_column("folders.id", nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Sibling folder names are unique (case-insensitive) among live folders; NULL parent = root level.
Index(
    "uq_folders_sibling_name_workspace",
    Folder.workspace_id,
    Folder.parent_folder_id,
    func.lower(Folder.name),
    unique=True,
    postgresql_nulls_not_distinct=True,
    postgresql_where=text("deleted_at IS NULL AND workspace_id IS NOT NULL"),
)
Index(
    "uq_folders_sibling_name_personal",
    Folder.owner_id,
    Folder.parent_folder_id,
    func.lower(Folder.name),
    unique=True,
    postgresql_nulls_not_distinct=True,
    postgresql_where=text("deleted_at IS NULL AND workspace_id IS NULL"),
)
