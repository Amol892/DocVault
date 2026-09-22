"""Share links (FR-10..15): owner-side management and the public, no-account access path.

The token is 256 random bits and only its SHA-256 hash is stored, so a database leak does not
yield working links. Revocation, expiry and the password are checked on EVERY access; nothing
about a link's validity is cached.
"""

import hashlib
import ipaddress
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ApiError, not_found
from app.core.security import hash_password, verify_password
from app.models.document import Document, DocumentVersion
from app.models.enums import ShareAccessOutcome, UploadStatus
from app.models.share_link import ShareLink, ShareLinkAccessLog
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.common import Paginated
from app.schemas.share_link import (
    PublicShareOut,
    ShareAccessLogOut,
    ShareLinkCreate,
    ShareLinkOut,
)
from app.services import activity
from app.services.access import DocumentAccess, ShareLinkAccess
from app.services.preview import PREVIEWABLE
from app.storage.base import StorageBackend

TOKEN_BYTES = 32
MAX_BAD_PASSWORDS = 10  # per link and client address...
LOCKOUT = timedelta(minutes=15)  # ...within this window
PUBLIC_URL_EXPIRE_SECONDS = 300
LOG_PAGE_SIZE = 50


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _is_expired(link: ShareLink, now: datetime) -> bool:
    return link.expires_at is not None and link.expires_at <= now


def _out(link: ShareLink, url: str | None = None) -> ShareLinkOut:
    return ShareLinkOut(
        id=link.id,
        document_id=link.document_id,
        url=url,
        allow_download=link.allow_download,
        has_password=link.password_hash is not None,
        expires_at=link.expires_at,
        expired=_is_expired(link, datetime.now(UTC)),
        revoked_at=link.revoked_at,
        created_at=link.created_at,
    )


async def list_links(session: AsyncSession, access: DocumentAccess) -> list[ShareLinkOut]:
    rows = await session.execute(
        select(ShareLink)
        .where(ShareLink.document_id == access.document.id)
        .order_by(ShareLink.created_at.desc(), ShareLink.id)
    )
    return [_out(link) for link in rows.scalars()]


async def create_link(
    session: AsyncSession, access: DocumentAccess, body: ShareLinkCreate
) -> ShareLinkOut:
    now = datetime.now(UTC)
    if body.expires_at is not None and body.expires_at <= now:
        raise ApiError(422, "VALIDATION_ERROR", "expires_at: must be in the future")
    token = secrets.token_urlsafe(TOKEN_BYTES)
    link = ShareLink(
        document_id=access.document.id,
        token_hash=hash_token(token),
        created_by=access.user.id,
        password_hash=hash_password(body.password) if body.password else None,
        expires_at=body.expires_at,
        allow_download=body.allow_download,
    )
    session.add(link)
    await session.flush()
    if access.document.workspace_id is not None:
        activity.record_activity(
            session,
            workspace_id=access.document.workspace_id,
            actor_id=access.user.id,
            action=activity.SHARE_LINK_CREATED,
            target_type="document",
            target_id=access.document.id,
            metadata={"link_id": link.id},
        )
    await session.commit()
    url = f"{get_settings().frontend_url.rstrip('/')}/s/{token}"
    return _out(link, url)


async def update_link(
    session: AsyncSession, access: ShareLinkAccess, allow_download: bool
) -> ShareLinkOut:
    """Flip whether the link permits download, without revoking and re-creating it (its address
    stays the same)."""
    link = access.link
    if link.allow_download != allow_download:
        link.allow_download = allow_download
        document = access.document.document
        if document.workspace_id is not None:
            activity.record_activity(
                session,
                workspace_id=document.workspace_id,
                actor_id=access.document.user.id,
                action=activity.SHARE_LINK_UPDATED,
                target_type="document",
                target_id=document.id,
                metadata={"link_id": link.id, "allow_download": allow_download},
            )
        await session.commit()
    return _out(link)


async def revoke_link(session: AsyncSession, access: ShareLinkAccess) -> None:
    """Idempotent: revoking a revoked link is not an error."""
    link = access.link
    if link.revoked_at is not None:
        return
    link.revoked_at = datetime.now(UTC)
    document = access.document.document
    if document.workspace_id is not None:
        activity.record_activity(
            session,
            workspace_id=document.workspace_id,
            actor_id=access.document.user.id,
            action=activity.SHARE_LINK_REVOKED,
            target_type="document",
            target_id=document.id,
            metadata={"link_id": link.id},
        )
    await session.commit()


async def list_access_log(
    session: AsyncSession, access: ShareLinkAccess, page: int
) -> Paginated[ShareAccessLogOut]:
    where = ShareLinkAccessLog.share_link_id == access.link.id
    total = (
        await session.execute(select(func.count()).select_from(ShareLinkAccessLog).where(where))
    ).scalar_one()
    rows = await session.execute(
        select(ShareLinkAccessLog)
        .where(where)
        .order_by(ShareLinkAccessLog.accessed_at.desc(), ShareLinkAccessLog.id)
        .limit(LOG_PAGE_SIZE)
        .offset((page - 1) * LOG_PAGE_SIZE)
    )
    return Paginated[ShareAccessLogOut](
        items=[
            ShareAccessLogOut(
                accessed_at=entry.accessed_at,
                ip_address=str(entry.ip_address) if entry.ip_address is not None else None,
                user_agent=entry.user_agent,
                outcome=entry.outcome.value,
            )
            for entry in rows.scalars()
        ],
        page=page,
        total=total,
    )


# ---- public access -------------------------------------------------------------------------


def _clean_ip(host: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


async def _log(
    session: AsyncSession,
    link: ShareLink,
    outcome: ShareAccessOutcome,
    ip: str | None,
    user_agent: str | None,
) -> None:
    session.add(
        ShareLinkAccessLog(
            share_link_id=link.id,
            ip_address=ip,
            user_agent=user_agent[:500] if user_agent else None,
            outcome=outcome,
        )
    )
    await session.commit()


async def _too_many_bad_passwords(session: AsyncSession, link: ShareLink, ip: str | None) -> bool:
    if ip is None:
        return False
    since = datetime.now(UTC) - LOCKOUT
    count = (
        await session.execute(
            select(func.count())
            .select_from(ShareLinkAccessLog)
            .where(
                ShareLinkAccessLog.share_link_id == link.id,
                ShareLinkAccessLog.outcome == ShareAccessOutcome.BAD_PASSWORD,
                ShareLinkAccessLog.ip_address == ip,
                ShareLinkAccessLog.accessed_at >= since,
            )
        )
    ).scalar_one()
    return bool(count >= MAX_BAD_PASSWORDS)


async def open_public_link(
    session: AsyncSession,
    storage: StorageBackend,
    *,
    token: str,
    password: str | None,
    ip: str | None,
    user_agent: str | None,
) -> PublicShareOut:
    """Resolve a link for a recipient who has no account. Every failure that does not name a
    real, currently valid link looks the same as a link that never existed (404)."""
    ip = _clean_ip(ip)
    row = (
        await session.execute(
            select(ShareLink, Document)
            .join(Document, Document.id == ShareLink.document_id)
            .where(ShareLink.token_hash == hash_token(token), Document.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        raise not_found("This link doesn't exist.")
    link, document = row
    if document.workspace_id is not None:
        workspace = await session.get(Workspace, document.workspace_id)
        if workspace is None or workspace.deleted_at is not None:
            raise not_found("This link doesn't exist.")
    owner = await session.get(User, document.owner_id)
    if owner is None or not owner.is_active:
        raise not_found("This link doesn't exist.")

    now = datetime.now(UTC)
    if link.revoked_at is not None:
        await _log(session, link, ShareAccessOutcome.REVOKED, ip, user_agent)
        raise ApiError(410, "LINK_REVOKED", "This link has been revoked.")
    if _is_expired(link, now):
        await _log(session, link, ShareAccessOutcome.EXPIRED, ip, user_agent)
        raise ApiError(410, "LINK_EXPIRED", "This link has expired.")

    if link.password_hash is not None:
        if password is None:
            return PublicShareOut(requires_password=True)  # nothing about the document yet
        if await _too_many_bad_passwords(session, link, ip):
            raise ApiError(
                429, "TOO_MANY_ATTEMPTS", "Too many wrong passwords. Try again in a while."
            )
        if not verify_password(password, link.password_hash):
            await _log(session, link, ShareAccessOutcome.BAD_PASSWORD, ip, user_agent)
            raise ApiError(403, "BAD_PASSWORD", "That password is wrong.")

    version = (
        (
            await session.execute(
                select(DocumentVersion)
                .where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.upload_status == UploadStatus.READY,
                )
                .order_by(DocumentVersion.version_number.desc())
            )
        )
        .scalars()
        .first()
    )
    if version is None:
        raise not_found("This link doesn't exist.")

    mime = version.mime_type or "application/octet-stream"
    download_url = None
    if link.allow_download:
        download_url = await storage.presign_download(
            version.storage_key,
            filename=document.filename,
            content_type=mime,
            expires_seconds=PUBLIC_URL_EXPIRE_SECONDS,
        )
    preview_url = None
    if mime in PREVIEWABLE:
        preview_url = await storage.presign_download(
            version.storage_key,
            filename=document.filename,
            content_type=mime,
            expires_seconds=PUBLIC_URL_EXPIRE_SECONDS,
            inline=True,
        )
    await _log(session, link, ShareAccessOutcome.OK, ip, user_agent)
    return PublicShareOut(
        requires_password=False,
        filename=document.filename,
        mime_type=mime,
        size_bytes=version.size_bytes or 0,
        allow_download=link.allow_download,
        expires_at=link.expires_at,
        download_url=download_url,
        preview_url=preview_url,
    )
