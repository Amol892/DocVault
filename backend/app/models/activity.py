from typing import Any

from sqlalchemy import Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column, id_column


class ActivityLog(RandomIdMixin, TimestampMixin, Base):
    """Append-only workspace audit trail (role, membership, ownership and guest-grant changes)."""

    __tablename__ = "activity_logs"

    workspace_id: Mapped[str | None] = fk_column(
        "workspaces.id", nullable=True
    )  # NULL: platform event
    actor_id: Mapped[str] = fk_column("users.id")
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = id_column(nullable=True)
    # "metadata" is reserved by SQLAlchemy's declarative base, so the attribute is metadata_.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )


Index(
    "ix_activity_logs_workspace_id_created_at",
    ActivityLog.workspace_id,
    ActivityLog.created_at.desc(),
)
