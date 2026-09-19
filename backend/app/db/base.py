from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base; import all models in app/models so Alembic sees them."""
