from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import (
    SessionDep,
    get_document_access,
    get_list_scope,
    get_trash_scope,
    get_trashed_document_access,
    get_upload_target,
    require_document,
)
from app.core.permissions import Action
from app.schemas.common import ErrorResponse, Paginated, Responses
from app.schemas.document import (
    DocumentOut,
    DocumentPatch,
    DocumentVersionOut,
    DownloadUrlResponse,
    GrantCreate,
    PreviewUrlResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services import documents
from app.services.access import DocumentAccess, ListScope, UploadTarget
from app.storage import get_storage
from app.storage.base import StorageBackend

router = APIRouter(prefix="/documents", tags=["documents"])

StorageDep = Annotated[StorageBackend, Depends(get_storage)]

_RESPONSES: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"},
    403: {"model": ErrorResponse, "description": "Your role does not allow this"},
    404: {"model": ErrorResponse, "description": "No such document, or no access"},
}


@router.get("", response_model=Paginated[DocumentOut], responses=_RESPONSES)
async def list_documents(
    scope: Annotated[ListScope, Depends(get_list_scope)],
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> Paginated[DocumentOut]:
    """Without `workspace_id`: your personal documents. Search matches filename or uploader."""
    return await documents.list_documents(session, scope, q, page)


@router.get("/trash", response_model=Paginated[DocumentOut], responses=_RESPONSES)
async def list_trash(
    scope: Annotated[ListScope, Depends(get_trash_scope)],
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
) -> Paginated[DocumentOut]:
    """Recently deleted documents that can still be restored (FR-7). Members and above only."""
    return await documents.list_documents(session, scope, None, page, trashed=True)


@router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    responses={
        **_RESPONSES,
        413: {"model": ErrorResponse, "description": "Larger than the upload limit"},
    },
)
async def create_upload_url(
    body: UploadUrlRequest,
    target: Annotated[UploadTarget, Depends(get_upload_target)],
    session: SessionDep,
    storage: StorageDep,
) -> UploadUrlResponse:
    """A short-lived pre-signed URL to PUT the file straight to storage. Send `document_id` to add
    a new version to an existing document."""
    return await documents.create_upload(session, storage, target, body)


@router.post(
    "/{document_id}/confirm-upload",
    response_model=DocumentOut,
    responses={
        **_RESPONSES,
        409: {"model": ErrorResponse, "description": "Nothing was uploaded"},
        422: {"model": ErrorResponse, "description": "The file failed validation"},
    },
)
async def confirm_upload(
    access: Annotated[DocumentAccess, Depends(require_document(Action.UPLOAD_DOCUMENT))],
    session: SessionDep,
    storage: StorageDep,
) -> DocumentOut:
    return await documents.confirm_upload(session, storage, access)


@router.get("/{document_id}/download-url", response_model=DownloadUrlResponse, responses=_RESPONSES)
async def get_download_url(
    access: Annotated[DocumentAccess, Depends(get_document_access)],
    session: SessionDep,
    storage: StorageDep,
) -> DownloadUrlResponse:
    return await documents.download_url(session, storage, access)


@router.get(
    "/{document_id}/preview-url",
    response_model=PreviewUrlResponse,
    responses={
        **_RESPONSES,
        415: {"model": ErrorResponse, "description": "This file type can't be previewed"},
    },
)
async def get_preview_url(
    access: Annotated[DocumentAccess, Depends(get_document_access)],
    session: SessionDep,
    storage: StorageDep,
) -> PreviewUrlResponse:
    """Renders inline in the browser (PDF, images, plain text); anything else is download-only."""
    return await documents.preview_url(session, storage, access)


@router.patch("/{document_id}", response_model=DocumentOut, responses=_RESPONSES)
async def patch_document(
    body: DocumentPatch,
    access: Annotated[DocumentAccess, Depends(require_document(Action.UPLOAD_DOCUMENT))],
    session: SessionDep,
) -> DocumentOut:
    """Rename (`filename`) or move (`folder_id`, null = root); exactly one per request."""
    if "filename" in body.model_fields_set:
        return await documents.rename_document(session, access, str(body.filename))
    return await documents.move_document(session, access, body.folder_id)


@router.delete("/{document_id}", status_code=204, responses=_RESPONSES)
async def delete_document(
    access: Annotated[DocumentAccess, Depends(require_document(Action.UPLOAD_DOCUMENT))],
    session: SessionDep,
) -> Response:
    await documents.delete_document(session, access)
    return Response(status_code=204)


@router.post("/{document_id}/grants", status_code=204, responses=_RESPONSES)
async def grant_document_access(
    body: GrantCreate,
    access: Annotated[DocumentAccess, Depends(require_document(Action.GRANT_DOCUMENT_ACCESS))],
    session: SessionDep,
) -> Response:
    """Give a Guest access to exactly this document (FR-21). Idempotent."""
    await documents.grant_document(session, access, body.user_id)
    return Response(status_code=204)


@router.delete("/{document_id}/grants/{user_id}", status_code=204, responses=_RESPONSES)
async def revoke_document_access(
    user_id: str,
    access: Annotated[DocumentAccess, Depends(require_document(Action.GRANT_DOCUMENT_ACCESS))],
    session: SessionDep,
) -> Response:
    await documents.revoke_document(session, access, user_id)
    return Response(status_code=204)


@router.post("/{document_id}/restore", response_model=DocumentOut, responses=_RESPONSES)
async def restore_document(
    access: Annotated[DocumentAccess, Depends(get_trashed_document_access)],
    session: SessionDep,
) -> DocumentOut:
    """Undo a delete within the grace period (FR-7)."""
    return await documents.restore_document(session, access)


@router.get(
    "/{document_id}/versions", response_model=list[DocumentVersionOut], responses=_RESPONSES
)
async def list_versions(
    access: Annotated[DocumentAccess, Depends(get_document_access)], session: SessionDep
) -> list[DocumentVersionOut]:
    return await documents.list_versions(session, access)


@router.get(
    "/{document_id}/versions/{version_number}/download-url",
    response_model=DownloadUrlResponse,
    responses=_RESPONSES,
)
async def get_version_download_url(
    version_number: int,
    access: Annotated[DocumentAccess, Depends(get_document_access)],
    session: SessionDep,
    storage: StorageDep,
) -> DownloadUrlResponse:
    return await documents.version_download_url(session, storage, access, version_number)
