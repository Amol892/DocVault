from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column
from app.models.enums import AuthTokenPurpose, db_enum


class AuthToken(RandomIdMixin, TimestampMixin, Base):
    """A single-use, expiring token sent by email: verify an address (FR-1) or reset a password
    (FR-4). Only the SHA-256 hash of the token is stored; the raw value exists only in the email.
    """

    __tablename__ = "auth_tokens"
    __table_args__ = (CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"),)

    user_id: Mapped[str] = fk_column("users.id", ondelete="CASCADE", index=True)
    purpose: Mapped[AuthTokenPurpose] = mapped_column(
        db_enum(AuthTokenPurpose, "auth_token_purpose")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
