"""Housekeeping the API never does inside a request: it removes what is past its grace period.

Everything here is safe to run repeatedly and at any time (see app/jobs/purge.py).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document import Document, DocumentVersion
from app.models.enums import UploadStatus
from app.models.share_link import ShareLink, ShareLinkAccessLog
from app.services.accounts import purge_expired_revoked_tokens
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


@dataclass
class PurgeReport:
    documents: int = 0
    stale_uploads: int = 0
    revoked_tokens: int = 0


async def _purge_expired_documents(
    session: AsyncSession, storage: StorageBackend, now: datetime
) -> int:
    """Hard-delete documents that were soft-deleted longer ago than the grace period: their
    stored objects, versions, share links and link logs go with them."""
    cutoff = now - timedelta(days=get_settings().trash_grace_days)
    ids = (
        (
            await session.execute(
                select(Document.id).where(
                    Document.deleted_at.is_not(None), Document.deleted_at < cutoff
                )
            )
        )
        .scalars()
        .all()
    )
    for document_id in ids:
        keys = (
            (
                await session.execute(
                    select(DocumentVersion.storage_key).where(
                        DocumentVersion.document_id == document_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for key in keys:
            await storage.delete(key)
        links = select(ShareLink.id).where(ShareLink.document_id == document_id)
        await session.execute(
            delete(ShareLinkAccessLog).where(ShareLinkAccessLog.share_link_id.in_(links))
        )
        await session.execute(delete(ShareLink).where(ShareLink.document_id == document_id))
        await session.execute(
            delete(DocumentVersion).where(DocumentVersion.document_id == document_id)
        )
        await session.execute(delete(Document).where(Document.id == document_id))
        await session.commit()
    return len(ids)


async def _abandon_stale_uploads(
    session: AsyncSession, storage: StorageBackend, now: datetime
) -> int:
    """An upload nobody confirmed within the TTL is abandoned: its object (if the browser did
    manage to put one) is deleted and the version is marked rejected. A document left with no
    usable version is soft-deleted, so it is purged after the grace period like any other."""
    cutoff = now - timedelta(hours=get_settings().pending_upload_ttl_hours)
    stale = (
        (
            await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.upload_status == UploadStatus.PENDING,
                    DocumentVersion.created_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    for version in stale:
        await storage.delete(version.storage_key)
        version.upload_status = UploadStatus.REJECTED
        has_ready = (
            await session.execute(
                select(
                    exists().where(
                        DocumentVersion.document_id == version.document_id,
                        DocumentVersion.upload_status == UploadStatus.READY,
                    )
                )
            )
        ).scalar_one()
        if not has_ready:
            document = await session.get(Document, version.document_id)
            if document is not None and document.deleted_at is None:
                document.deleted_at = now
        await session.commit()
    return len(stale)


async def purge(
    session: AsyncSession, storage: StorageBackend, *, now: datetime | None = None
) -> PurgeReport:
    now = now or datetime.now(UTC)
    report = PurgeReport()
    report.stale_uploads = await _abandon_stale_uploads(session, storage, now)
    report.documents = await _purge_expired_documents(session, storage, now)
    report.revoked_tokens = await purge_expired_revoked_tokens(session)
    await session.commit()
    logger.info("purge finished: %s", report)
    return report
