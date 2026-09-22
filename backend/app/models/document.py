from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RandomIdMixin, TimestampMixin, fk_column, id_column
from app.models.enums import UploadStatus, db_enum


class Document(RandomIdMixin, TimestampMixin, Base):
    """One row per logical document (metadata only). Bytes live in object storage.

    workspace_id NULL means a personal document owned by owner_id. The current version is the
    document_versions row with the highest version_number (versions are append-only, so the newest
    is always current). There is deliberately no back-reference column: it would make
    documents <-> document_versions circular, and Alembic autogenerate cannot create a circular FK.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            r"length(filename) BETWEEN 1 AND 255 AND filename !~ '[/\\]'", name="filename_valid"
        ),
        # target of the composite foreign key from document_grants
        UniqueConstraint("id", "workspace_id", name="uq_documents_id_workspace_id"),
        Index(
            "ix_documents_workspace_id_folder_id_live",
            "workspace_id",
            "folder_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_documents_personal_owner_id",
            "owner_id",
            postgresql_where=text("workspace_id IS NULL"),
        ),
    )

    workspace_id: Mapped[str | None] = fk_column("workspaces.id", nullable=True)
    owner_id: Mapped[str] = fk_column("users.id")
    folder_id: Mapped[str | None] = fk_column("folders.id", nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Case-insensitive filename lookup for search/filter (add a trigram index with the search FR).
Index("ix_documents_filename_lower", func.lower(Document.filename))


class DocumentVersion(RandomIdMixin, TimestampMixin, Base):
    """Append-only version history; re-uploading adds a row and never overwrites."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_id_version_number"
        ),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        CheckConstraint("checksum_sha256 ~ '^[0-9a-f]{64}$'", name="checksum_sha256_format"),
    )

    document_id: Mapped[str] = fk_column("documents.id")
    version_number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)  # opaque, server-generated
    # Full S3 object URL (address only). The bucket is private: clients only get pre-signed URLs
    # minted from storage_key after the authorization check. Never return this to a client.
    storage_url: Mapped[str] = mapped_column(Text, unique=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(Text)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    upload_status: Mapped[UploadStatus] = mapped_column(
        db_enum(UploadStatus, "upload_status"), server_default=UploadStatus.PENDING.value
    )
    created_by: Mapped[str] = fk_column("users.id")


class DocumentGrant(RandomIdMixin, TimestampMixin, Base):
    """Scopes a Guest to exactly one document (FR-21). Deleting the row revokes access.

    Grants are folder-pinned: they apply to the document wherever it currently is, but moving the
    document to a different folder (directly, or indirectly when the folder it was in gets deleted
    and its contents re-parented, FR-23) revokes them — see services/documents.py and
    services/folders.py, which delete the row whenever a granted document's folder_id changes.
    """

    __tablename__ = "document_grants"
    __table_args__ = (
        UniqueConstraint("document_id", "user_id", name="uq_document_grants_document_id_user_id"),
        # the document must belong to the same workspace
        ForeignKeyConstraint(
            ["document_id", "workspace_id"],
            ["documents.id", "documents.workspace_id"],
            name="fk_document_grants_document_id_documents",
            ondelete="CASCADE",
        ),
        # removing the membership removes the grants in the same statement (immediate revocation)
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspace_members.workspace_id", "workspace_members.user_id"],
            name="fk_document_grants_workspace_id_workspace_members",
            ondelete="CASCADE",
        ),
        Index("ix_document_grants_workspace_id_user_id", "workspace_id", "user_id"),
    )

    workspace_id: Mapped[str] = id_column()
    document_id: Mapped[str] = id_column()
    user_id: Mapped[str] = id_column()
    granted_by: Mapped[str] = fk_column("users.id")
