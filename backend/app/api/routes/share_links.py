from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import SessionDep, get_share_link_access, require_document
from app.core.permissions import Action
from app.schemas.common import ErrorResponse, Paginated, Responses
from app.schemas.share_link import ShareAccessLogOut, ShareLinkCreate, ShareLinkOut, ShareLinkPatch
from app.services import share_links
from app.services.access import DocumentAccess, ShareLinkAccess

router = APIRouter(tags=["share-links"])

_RESPONSES: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"},
    403: {"model": ErrorResponse, "description": "Your role does not allow sharing"},
    404: {"model": ErrorResponse, "description": "No such document or link, or no access"},
}

CanShare = Annotated[DocumentAccess, Depends(require_document(Action.CREATE_SHARE_LINK))]
ManagedLink = Annotated[ShareLinkAccess, Depends(get_share_link_access)]


@router.get(
    "/documents/{document_id}/share-links", response_model=list[ShareLinkOut], responses=_RESPONSES
)
async def list_share_links(access: CanShare, session: SessionDep) -> list[ShareLinkOut]:
    """Every link for the document, newest first. The address is never included."""
    return await share_links.list_links(session, access)


@router.post(
    "/documents/{document_id}/share-links",
    status_code=201,
    response_model=ShareLinkOut,
    responses=_RESPONSES,
)
async def create_share_link(
    body: ShareLinkCreate, access: CanShare, session: SessionDep
) -> ShareLinkOut:
    """The only response that carries the link's `url`; it cannot be shown again (FR-10)."""
    return await share_links.create_link(session, access, body)


@router.patch("/share-links/{link_id}", response_model=ShareLinkOut, responses=_RESPONSES)
async def update_share_link(
    body: ShareLinkPatch, access: ManagedLink, session: SessionDep
) -> ShareLinkOut:
    """Change whether the link allows download, without revoking it (the address stays valid)."""
    return await share_links.update_link(session, access, body.allow_download)


@router.delete("/share-links/{link_id}", status_code=204, responses=_RESPONSES)
async def revoke_share_link(access: ManagedLink, session: SessionDep) -> Response:
    """Takes effect on the very next access (FR-13)."""
    await share_links.revoke_link(session, access)
    return Response(status_code=204)


@router.get(
    "/share-links/{link_id}/access-log",
    response_model=Paginated[ShareAccessLogOut],
    responses=_RESPONSES,
)
async def share_link_access_log(
    access: ManagedLink,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
) -> Paginated[ShareAccessLogOut]:
    """Who opened the link and when (FR-14), for whoever manages it."""
    return await share_links.list_access_log(session, access, page)
