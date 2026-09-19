from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column
from app.models.enums import ShareAccessOutcome, db_enum


class ShareLink(RandomIdMixin, TimestampMixin, Base):
    """External, token-based access to exactly one document. Revocation is a flag, not a delete."""

    __tablename__ = "share_links"
    __table_args__ = (CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"),)

    document_id: Mapped[str] = fk_column("documents.id", index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of a >=128-bit token
    created_by: Mapped[str] = fk_column("users.id")
    password_hash: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allow_download: Mapped[bool] = mapped_column(server_default=text("true"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShareLinkAccessLog(RandomIdMixin, TimestampMixin, Base):
    """Append-only audit trail of link usage."""

    __tablename__ = "share_link_access_logs"

    share_link_id: Mapped[str] = fk_column("share_links.id")
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[ShareAccessOutcome] = mapped_column(
        db_enum(ShareAccessOutcome, "share_access_outcome")
    )


Index(
    "ix_share_link_access_logs_share_link_id_accessed_at",
    ShareLinkAccessLog.share_link_id,
    ShareLinkAccessLog.accessed_at.desc(),
)
