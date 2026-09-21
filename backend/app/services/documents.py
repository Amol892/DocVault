from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ApiError, not_found
from app.models.document import Document, DocumentVersion
from app.models.enums import UploadStatus, WorkspaceRole
from app.models.share_link import ShareLink
from app.models.user import User
from app.schemas.common import Paginated
from app.schemas.document import (
    DocumentOut,
    DownloadUrlResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services.access import (
    DocumentAccess,
    ListScope,
    UploadTarget,
    get_live_folder,
    guest_visible_folder_ids,
)
from app.services.upload_validation import check_upload, normalize_mime
from app.storage.base import StorageBackend

PAGE_SIZE = 50
SNIFF_BYTES = 512


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _documents_query() -> Select[Any]:
    """Live documents that have a ready version, as rows of (document, current version, owner
    name, has an active share link). The current version is the highest-numbered ready one."""
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
        .where(Document.deleted_at.is_(None))
    )


def _to_out(row: Any) -> DocumentOut:
    document, version, owner_name, is_public = row
    if document.workspace_id is None:
        visibility = "private"
    else:
        visibility = "public" if is_public else "workspace"
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


async def get_document_out(session: AsyncSession, document_id: str) -> DocumentOut:
    # the ORM identity map may hold stale copies from before a commit in this request
    session.expire_all()
    row = (await session.execute(_documents_query().where(Document.id == document_id))).first()
    if row is None:
        raise not_found("Document not found.")
    return _to_out(row)


async def list_documents(
    session: AsyncSession, scope: ListScope, q: str | None, page: int
) -> Paginated[DocumentOut]:
    query = _documents_query()
    if scope.workspace is None:
        query = query.where(Document.workspace_id.is_(None), Document.owner_id == scope.user.id)
    else:
        workspace_id = scope.workspace.workspace.id
        query = query.where(Document.workspace_id == workspace_id)
        if scope.folder_id is not None:
            query = query.where(Document.folder_id == scope.folder_id)
        elif scope.workspace.role == WorkspaceRole.GUEST:
            visible = await guest_visible_folder_ids(session, workspace_id, scope.user.id)
            query = query.where(Document.folder_id.in_(visible))
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
        query.order_by(Document.created_at.desc(), Document.id)
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
    document.folder_id = folder_id
    await session.commit()
    return await get_document_out(session, document.id)


async def delete_document(session: AsyncSession, access: DocumentAccess) -> None:
    """Soft delete: the row and the stored objects stay for the grace period."""
    access.document.deleted_at = datetime.now(UTC)
    await session.commit()
