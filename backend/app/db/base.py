from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column

from app.core.ids import ID_LENGTH, generate_random_id

# Deterministic constraint names: stable Alembic revisions, and constraints can be dropped by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base; import all models in app/models so Alembic sees them."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class RandomIdMixin:
    """Random, non-sequential primary key. Inherited by every model."""

    id: Mapped[str] = mapped_column(
        String(ID_LENGTH), primary_key=True, default=generate_random_id, sort_order=-10
    )


class TimestampMixin:
    """created_at / updated_at on every model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), sort_order=1000
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), sort_order=1001
    )


def id_column(*, nullable: bool = False) -> MappedColumn[Any]:
    """A plain id-typed column (used where a composite foreign key carries the reference)."""
    return mapped_column(String(ID_LENGTH), nullable=nullable)


def fk_column(
    target: str,
    *,
    nullable: bool = False,
    ondelete: str | None = None,
    index: bool = False,
) -> MappedColumn[Any]:
    """A foreign key to another table's random id."""
    return mapped_column(
        String(ID_LENGTH), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index
    )
