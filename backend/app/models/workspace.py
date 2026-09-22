from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column
from app.models.enums import WorkspaceRole, db_enum


class Workspace(RandomIdMixin, TimestampMixin, Base):
    """A tenant / team. Soft-deleted first; a later purge job hard-deletes after a grace period."""

    __tablename__ = "workspaces"
    __table_args__ = (CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),)

    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[str] = fk_column("users.id", index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkspaceMember(RandomIdMixin, TimestampMixin, Base):
    """Membership and role. Deleting the row is the whole revocation mechanism."""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_members_workspace_id_user_id"
        ),
        # at most one owner per workspace
        Index(
            "uq_workspace_members_one_owner",
            "workspace_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )

    workspace_id: Mapped[str] = fk_column("workspaces.id", ondelete="CASCADE")
    user_id: Mapped[str] = fk_column("users.id", index=True)
    role: Mapped[WorkspaceRole] = mapped_column(db_enum(WorkspaceRole, "workspace_role"))
    invited_by: Mapped[str | None] = fk_column("users.id", nullable=True)


class WorkspaceInvite(RandomIdMixin, TimestampMixin, Base):
    """Pending invitation by email. Only the SHA-256 hash of the token is stored."""

    __tablename__ = "workspace_invites"
    __table_args__ = (
        # ownership is only ever transferred, never invited
        CheckConstraint("role IN ('admin', 'member', 'guest')", name="role_not_owner"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"),
        # no duplicate pending invite for the same email
        Index(
            "uq_workspace_invites_pending",
            "workspace_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = fk_column("workspaces.id", ondelete="CASCADE", index=True)
    email: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(10))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[str] = fk_column("users.id")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkspaceInviteDocument(RandomIdMixin, TimestampMixin, Base):
    """Documents a Guest invite is granted on acceptance (FR-21)."""

    __tablename__ = "workspace_invite_documents"
    __table_args__ = (
        UniqueConstraint(
            "invite_id", "document_id", name="uq_workspace_invite_documents_invite_id_document_id"
        ),
    )

    invite_id: Mapped[str] = fk_column("workspace_invites.id", ondelete="CASCADE")
    document_id: Mapped[str] = fk_column("documents.id", ondelete="CASCADE", index=True)
