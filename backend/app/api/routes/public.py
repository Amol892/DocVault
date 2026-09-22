from fastapi import APIRouter, Request

from app.api.deps import SessionDep
from app.api.routes.documents import StorageDep
from app.schemas.common import ErrorResponse, Responses
from app.schemas.share_link import PublicShareOut, PublicShareRequest
from app.services import share_links

# No authentication here by design (FR-11): the link token is the credential.
router = APIRouter(prefix="/public", tags=["public"])

_RESPONSES: Responses = {
    403: {"model": ErrorResponse, "description": "Wrong password"},
    404: {"model": ErrorResponse, "description": "No such link"},
    410: {"model": ErrorResponse, "description": "The link was revoked or has expired"},
    429: {"model": ErrorResponse, "description": "Too many wrong passwords"},
}


@router.post("/share/{token}/access", response_model=PublicShareOut, responses=_RESPONSES)
async def open_share_link(
    token: str,
    body: PublicShareRequest,
    request: Request,
    session: SessionDep,
    storage: StorageDep,
) -> PublicShareOut:
    """Validates the link on every call and returns only that one document's details plus
    short-lived URLs (FR-12, FR-13, FR-15). A password-protected link answers
    `requires_password` until the right password is sent."""
    return await share_links.open_public_link(
        session,
        storage,
        token=token,
        password=body.password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
