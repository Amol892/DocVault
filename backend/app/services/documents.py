from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ApiError, not_found
from app.models.document import Document, DocumentGrant, DocumentVersion
from app.models.enums import UploadStatus, WorkspaceRole
from app.models.share_link import ShareLink
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.schemas.common import Paginated
from app.schemas.document import (
    DocumentOut,
    DocumentVersionOut,
    DownloadUrlResponse,
    PreviewUrlResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services import activity
from app.services.access import (
    DocumentAccess,
    ListScope,
    UploadTarget,
    get_live_folder,
    guest_visible_document_ids,
)
from app.services.preview import PREVIEWABLE
from app.services.upload_validation import check_upload, normalize_mime
from app.storage.base import StorageBackend

PAGE_SIZE = 50
SNIFF_BYTES = 512


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _documents_query(*, trashed: bool = False) -> Select[Any]:
    """Live (or, with `trashed`, recently soft-deleted) documents that have a ready version, as
    rows of (document, current version, owner name, has an active share link). The current
    version is the highest-numbered ready one."""
    latest = (
        select(
            DocumentVersion.document_id.label("document_id"),
            func.max(DocumentVersion.version_number).label("version_number"),
        )
        .where(DocumentVersion.upload_status == UploadStatus.READY)
        .group_by(DocumentVersion.document_id)
        .subquery()
    )
    now = datetime.now(UTC)
    is_public = exists().where(
        ShareLink.document_id == Document.id,
        ShareLink.revoked_at.is_(None),
        or_(ShareLink.expires_at.is_(None), ShareLink.expires_at > now),
    )
    return (
        select(Document, DocumentVersion, User.name, is_public)
        .join(latest, latest.c.document_id == Document.id)
        .join(
            DocumentVersion,
            and_(
                DocumentVersion.document_id == latest.c.document_id,
                DocumentVersion.version_number == latest.c.version_number,
            ),
        )
        .join(User, User.id == Document.owner_id)
        .where(_trash_condition(now) if trashed else Document.deleted_at.is_(None))
    )


def _trash_condition(now: datetime) -> Any:
    cutoff = now - timedelta(days=get_settings().trash_grace_days)
    return Document.deleted_at >= cutoff


def _to_out(row: Any) -> DocumentOut:
    document, version, owner_name, is_public = row
    if is_public:
        visibility = "public"
    else:
        visibility = "private" if document.workspace_id is None else "workspace"
    return DocumentOut(
        id=document.id,
        owner_id=document.owner_id,
        owner_name=owner_name,
        workspace_id=document.workspace_id,
        folder_id=document.folder_id,
        filename=document.filename,
        mime_type=version.mime_type or "application/octet-stream",
        size_bytes=version.size_bytes or 0,
        visibility=visibility,
        deleted_at=document.deleted_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


async def get_document_out(
    session: AsyncSession, document_id: str, *, trashed: bool = False
) -> DocumentOut:
    # the ORM identity map may hold stale copies from before a commit in this request
    session.expire_all()
    query = _documents_query(trashed=trashed).where(Document.id == document_id)
    row = (await session.execute(query)).first()
    if row is None:
        raise not_found("Document not found.")
    return _to_out(row)


async def list_documents(
    session: AsyncSession, scope: ListScope, q: str | None, page: int, *, trashed: bool = False
) -> Paginated[DocumentOut]:
    query = _documents_query(trashed=trashed)
    if scope.workspace is None:
        query = query.where(Document.workspace_id.is_(None), Document.owner_id == scope.user.id)
    else:
        workspace_id = scope.workspace.workspace.id
        query = query.where(Document.workspace_id == workspace_id)
        if scope.workspace.role == WorkspaceRole.GUEST:
            # flat set of exactly what was individually granted (FR-21) — never folder-scoped
            visible = await guest_visible_document_ids(session, workspace_id, scope.user.id)
            query = query.where(Document.id.in_(visible))
        elif scope.folder_id is not None and not trashed:
            query = query.where(Document.folder_id == scope.folder_id)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip().lower())}%"
        query = query.where(
            or_(
                func.lower(Document.filename).like(pattern, escape="\\"),
                func.lower(User.name).like(pattern, escape="\\"),
            )
        )
    total = (
        await session.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    ).scalar_one()
    rows = await session.execute(
        query.order_by(
            (Document.deleted_at if trashed else Document.created_at).desc(), Document.id
        )
        .limit(PAGE_SIZE)
        .offset((page - 1) * PAGE_SIZE)
    )
    return Paginated[DocumentOut](items=[_to_out(row) for row in rows], page=page, total=total)


async def create_upload(
    session: AsyncSession, storage: StorageBackend, target: UploadTarget, body: UploadUrlRequest
) -> UploadUrlResponse:
    settings = get_settings()
    if body.size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise ApiError(413, "FILE_TOO_LARGE", f"Files can be at most {settings.max_upload_mb} MB.")
    mime = normalize_mime(body.mime_type)

    if target.document is None:
        document = Document(
            workspace_id=target.workspace.workspace.id if target.workspace else None,
            owner_id=target.user.id,
            folder_id=target.folder_id,
            filename=body.filename,
        )
        session.add(document)
        await session.flush()
        version_number = 1
    else:
        # lock the document so two concurrent re-uploads get different version numbers
        document = (
            await session.execute(
                select(Document).where(Document.id == target.document.id).with_for_update()
            )
        ).scalar_one()
        highest = (
            await session.execute(
                select(func.max(DocumentVersion.version_number)).where(
                    DocumentVersion.document_id == document.id
                )
            )
        ).scalar_one()
        version_number = (highest or 0) + 1

    # opaque and server-generated: never derived from the filename (FR-6)
    prefix = f"w/{document.workspace_id}" if document.workspace_id else f"u/{document.owner_id}"
    key = f"{prefix}/{document.id}/{version_number}"
    session.add(
        DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            storage_key=key,
            storage_url=storage.object_url(key),
            size_bytes=body.size_bytes,
            mime_type=mime,
            upload_status=UploadStatus.PENDING,
            created_by=target.user.id,
        )
    )
    document_id = document.id
    await session.commit()
    url = await storage.presign_upload(
        key,
        content_type=mime,
        size_bytes=body.size_bytes,
        expires_seconds=settings.upload_url_expire_seconds,
    )
    return UploadUrlResponse(upload_url=url, storage_key=key, document_id=document_id)


async def _has_ready_version(session: AsyncSession, document_id: str) -> bool:
    result = await session.execute(
        select(
            exists().where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.upload_status == UploadStatus.READY,
            )
        )
    )
    return bool(result.scalar_one())


async def _latest_version(
    session: AsyncSession, document_id: str, status: UploadStatus, created_by: str | None = None
) -> DocumentVersion | None:
    statement = select(DocumentVersion).where(
        DocumentVersion.document_id == document_id, DocumentVersion.upload_status == status
    )
    if created_by is not None:
        statement = statement.where(DocumentVersion.created_by == created_by)
    result = await session.execute(statement.order_by(DocumentVersion.version_number.desc()))
    return result.scalars().first()


async def confirm_upload(
    session: AsyncSession, storage: StorageBackend, access: DocumentAccess
) -> DocumentOut:
    document = access.document
    pending = await _latest_version(session, document.id, UploadStatus.PENDING, access.user.id)
    if pending is None:
        if await _has_ready_version(session, document.id):
            return await get_document_out(session, document.id)  # already confirmed
        raise ApiError(409, "UPLOAD_NOT_FOUND", "No upload is waiting to be confirmed.")

    info = await storage.head(pending.storage_key)
    if info is None:
        raise ApiError(409, "UPLOAD_NOT_FOUND", "The file has not been uploaded yet.")
    head = await storage.read_prefix(pending.storage_key, SNIFF_BYTES)
    problem = check_upload(
        declared_mime=pending.mime_type or "",
        declared_size=pending.size_bytes or 0,
        stored_size=info.size_bytes,
        stored_content_type=info.content_type,
        head=head,
        max_bytes=get_settings().max_upload_mb * 1024 * 1024,
    )
    if problem is not None:
        key = pending.storage_key
        pending.upload_status = UploadStatus.REJECTED
        if not await _has_ready_version(session, document.id):
            document.deleted_at = datetime.now(UTC)  # a document with no usable file is nothing
        await session.commit()
        await storage.delete(key)
        raise ApiError(422, "UPLOAD_REJECTED", problem)

    pending.upload_status = UploadStatus.READY
    await session.commit()
    return await get_document_out(session, document.id)


async def download_url(
    session: AsyncSession, storage: StorageBackend, access: DocumentAccess
) -> DownloadUrlResponse:
    document = access.document
    version = await _latest_version(session, document.id, UploadStatus.READY)
    if version is None:
        raise not_found("Document not found.")
    expires = get_settings().download_url_expire_seconds
    url = await storage.presign_download(
        version.storage_key,
        filename=document.filename,
        content_type=version.mime_type or "application/octet-stream",
        expires_seconds=expires,
    )
    return DownloadUrlResponse(download_url=url, expires_in=expires)


async def preview_url(
    session: AsyncSession, storage: StorageBackend, access: DocumentAccess
) -> PreviewUrlResponse:
    """An inline-rendering URL for logged-in viewing, for the common types a browser can safely
    show without running anything from the file (same allowlist as the public share preview).
    Anything else is only ever a download."""
    document = access.document
    version = await _latest_version(session, document.id, UploadStatus.READY)
    if version is None:
        raise not_found("Document not found.")
    mime = version.mime_type or "application/octet-stream"
    if mime not in PREVIEWABLE:
        raise ApiError(415, "NOT_PREVIEWABLE", "This file type can't be previewed.")
    expires = get_settings().download_url_expire_seconds
    url = await storage.presign_download(
        version.storage_key,
        filename=document.filename,
        content_type=mime,
        expires_seconds=expires,
        inline=True,
    )
    return PreviewUrlResponse(preview_url=url, expires_in=expires)


async def rename_document(
    session: AsyncSession, access: DocumentAccess, filename: str
) -> DocumentOut:
    access.document.filename = filename
    await session.commit()
    return await get_document_out(session, access.document.id)


async def move_document(
    session: AsyncSession, access: DocumentAccess, folder_id: str | None
) -> DocumentOut:
    document = access.document
    if folder_id is not None:
        # personal documents have no folders; a workspace document stays in its own workspace
        live = (
            document.workspace_id is not None
            and await get_live_folder(session, document.workspace_id, folder_id) is not None
        )
        if not live:
            raise not_found("Folder not found.")
    if document.folder_id != folder_id:
        # grants are folder-pinned (FR-21): moving the document out of its granted folder
        # revokes them, whether it moves into another folder or to the workspace root
        await session.execute(delete(DocumentGrant).where(DocumentGrant.document_id == document.id))
    document.folder_id = folder_id
    await session.commit()
    return await get_document_out(session, document.id)


async def delete_document(session: AsyncSession, access: DocumentAccess) -> None:
    """Soft delete: the row and the stored objects stay for the grace period."""
    access.document.deleted_at = datetime.now(UTC)
    await session.commit()


async def restore_document(session: AsyncSession, access: DocumentAccess) -> DocumentOut:
    """Bring a soft-deleted document back. If its folder was deleted meanwhile it returns to the
    workspace root, so a restored document is never stranded in a folder nobody can open."""
    document = access.document
    cutoff = datetime.now(UTC) - timedelta(days=get_settings().trash_grace_days)
    if document.deleted_at is None or document.deleted_at < cutoff:
        raise not_found("Document not found.")
    original_folder_id = document.folder_id
    if document.folder_id is not None and (
        document.workspace_id is None
        or await get_live_folder(session, document.workspace_id, document.folder_id) is None
    ):
        document.folder_id = None
    if document.folder_id != original_folder_id:
        # its folder is gone, so it landed at the root: grants are folder-pinned (FR-21)
        await session.execute(delete(DocumentGrant).where(DocumentGrant.document_id == document.id))
    document.deleted_at = None
    await session.commit()
    return await get_document_out(session, document.id)


async def list_versions(session: AsyncSession, access: DocumentAccess) -> list[DocumentVersionOut]:
    """The confirmed versions, newest first. The first one is the current version."""
    rows = (
        await session.execute(
            select(DocumentVersion, User.name)
            .join(User, User.id == DocumentVersion.created_by)
            .where(
                DocumentVersion.document_id == access.document.id,
                DocumentVersion.upload_status == UploadStatus.READY,
            )
            .order_by(DocumentVersion.version_number.desc())
        )
    ).all()
    return [
        DocumentVersionOut(
            version_number=version.version_number,
            size_bytes=version.size_bytes or 0,
            mime_type=version.mime_type or "application/octet-stream",
            created_by_name=name,
            created_at=version.created_at,
            is_current=index == 0,
        )
        for index, (version, name) in enumerate(rows)
    ]


async def version_download_url(
    session: AsyncSession, storage: StorageBackend, access: DocumentAccess, version_number: int
) -> DownloadUrlResponse:
    version = (
        await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == access.document.id,
                DocumentVersion.version_number == version_number,
                DocumentVersion.upload_status == UploadStatus.READY,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        raise not_found("Version not found.")
    expires = get_settings().download_url_expire_seconds
    url = await storage.presign_download(
        version.storage_key,
        filename=access.document.filename,
        content_type=version.mime_type or "application/octet-stream",
        expires_seconds=expires,
    )
    return DownloadUrlResponse(download_url=url, expires_in=expires)


async def grant_document(
    session: AsyncSession, access: DocumentAccess, target_user_id: str
) -> None:
    """Give a Guest access to this one document (FR-21). Idempotent."""
    if access.workspace is None:  # personal documents have no workspace, so no Guests either
        raise not_found("Document not found.")
    workspace_id = access.workspace.workspace.id
    member = (
        await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == target_user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise not_found("Member not found.")
    if member.role != WorkspaceRole.GUEST:
        raise ApiError(409, "NOT_A_GUEST", "Only guests are given access to individual documents.")

    existing = await session.execute(
        select(DocumentGrant.id).where(
            DocumentGrant.document_id == access.document.id, DocumentGrant.user_id == target_user_id
        )
    )
    if existing.first() is not None:
        return
    session.add(
        DocumentGrant(
            workspace_id=workspace_id,
            document_id=access.document.id,
            user_id=target_user_id,
            granted_by=access.user.id,
        )
    )
    activity.record_activity(
        session,
        workspace_id=workspace_id,
        actor_id=access.user.id,
        action=activity.GUEST_DOCUMENT_GRANTED,
        target_type="user",
        target_id=target_user_id,
        metadata={"document_id": access.document.id},
    )
    await session.commit()


async def revoke_document(
    session: AsyncSession, access: DocumentAccess, target_user_id: str
) -> None:
    """Take a Guest's access to this document away, effective on their next request. Idempotent."""
    if access.workspace is None:
        raise not_found("Document not found.")
    result = await session.execute(
        delete(DocumentGrant).where(
            DocumentGrant.document_id == access.document.id, DocumentGrant.user_id == target_user_id
        )
    )
    if result.rowcount:  # type: ignore[attr-defined]
        activity.record_activity(
            session,
            workspace_id=access.workspace.workspace.id,
            actor_id=access.user.id,
            action=activity.GUEST_DOCUMENT_REVOKED,
            target_type="user",
            target_id=target_user_id,
            metadata={"document_id": access.document.id},
        )
    await session.commit()
