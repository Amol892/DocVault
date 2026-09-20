from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column


class RevokedToken(RandomIdMixin, TimestampMixin, Base):
    """Blacklist of JWTs revoked by logout. created_at is the moment of revocation.

    A JWT is stateless and stays valid until it expires, so logging out means remembering the
    token's jti here; the API rejects any token whose jti is listed. Once expires_at has passed
    the token is invalid anyway and the row can be deleted.
    """

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = fk_column("users.id", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
