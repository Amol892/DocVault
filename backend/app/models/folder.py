from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column, id_column


class Folder(RandomIdMixin, TimestampMixin, Base):
    """Folder hierarchy. workspace_id NULL means a personal folder owned by owner_id."""

    __tablename__ = "folders"
    __table_args__ = (
        CheckConstraint(r"length(name) BETWEEN 1 AND 255 AND name !~ '[/\\]'", name="name_valid"),
        # target of the composite foreign key from folder_grants
        UniqueConstraint("id", "workspace_id", name="uq_folders_id_workspace_id"),
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


class FolderGrant(RandomIdMixin, TimestampMixin, Base):
    """Scopes a Guest to a folder (and its descendants). Deleting the row revokes access."""

    __tablename__ = "folder_grants"
    __table_args__ = (
        UniqueConstraint("folder_id", "user_id", name="uq_folder_grants_folder_id_user_id"),
        # the folder must belong to the same workspace
        ForeignKeyConstraint(
            ["folder_id", "workspace_id"],
            ["folders.id", "folders.workspace_id"],
            name="fk_folder_grants_folder_id_folders",
            ondelete="CASCADE",
        ),
        # removing the membership removes the grants in the same statement (immediate revocation)
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspace_members.workspace_id", "workspace_members.user_id"],
            name="fk_folder_grants_workspace_id_workspace_members",
            ondelete="CASCADE",
        ),
        Index("ix_folder_grants_workspace_id_user_id", "workspace_id", "user_id"),
    )

    workspace_id: Mapped[str] = id_column()
    folder_id: Mapped[str] = id_column()
    user_id: Mapped[str] = id_column()
    granted_by: Mapped[str] = fk_column("users.id")
