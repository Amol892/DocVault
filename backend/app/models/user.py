from sqlalchemy import CheckConstraint, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin


class User(RandomIdMixin, TimestampMixin, Base):
    """Account identity. Never hard-deleted: deactivate instead, to keep owner/creator history."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),)

    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


# Case-insensitive unique email (no citext extension needed); the app lower-cases on write.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
