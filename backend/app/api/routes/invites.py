from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, SessionDep, require
from app.core.permissions import Action
from app.schemas.common import ErrorResponse, Responses
from app.schemas.invite import InviteCreate, InviteOut, InvitePreviewOut
from app.services import invites
from app.services.access import WorkspaceAccess
from app.services.mailer import Mailer, get_mailer

router = APIRouter(tags=["invites"])

MailerDep = Annotated[Mailer, Depends(get_mailer)]
CanInvite = Annotated[WorkspaceAccess, Depends(require(Action.INVITE_MEMBER))]

_RESPONSES: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"},
    403: {"model": ErrorResponse, "description": "Your role does not allow this"},
    404: {"model": ErrorResponse, "description": "No such workspace or invite"},
    409: {"model": ErrorResponse, "description": "Already a member, or an invite is pending"},
    410: {"model": ErrorResponse, "description": "The invitation expired, was revoked or used"},
}


@router.post(
    "/workspaces/{workspace_id}/invites",
    status_code=201,
    response_model=InviteOut,
    responses=_RESPONSES,
)
async def create_invite(
    body: InviteCreate, access: CanInvite, session: SessionDep, mailer: MailerDep
) -> InviteOut:
    """Emails the invitation and also returns its `url` once, so an admin can hand it over if the
    email does not arrive (FR-18)."""
    return await invites.create_invite(session, mailer, access, body)


@router.get(
    "/workspaces/{workspace_id}/invites", response_model=list[InviteOut], responses=_RESPONSES
)
async def list_invites(access: CanInvite, session: SessionDep) -> list[InviteOut]:
    """Invitations still waiting to be accepted."""
    return await invites.list_invites(session, access.workspace.id)


@router.delete(
    "/workspaces/{workspace_id}/invites/{invite_id}", status_code=204, responses=_RESPONSES
)
async def revoke_invite(invite_id: str, access: CanInvite, session: SessionDep) -> Response:
    await invites.revoke_invite(session, access, invite_id)
    return Response(status_code=204)


@router.get("/invites/{token}", response_model=InvitePreviewOut, responses=_RESPONSES)
async def preview_invite(token: str, session: SessionDep) -> InvitePreviewOut:
    """What an invitation is for, before signing in to accept it. The token is the credential."""
    return await invites.preview_invite(session, token)


@router.post("/invites/{token}/accept", status_code=204, responses=_RESPONSES)
async def accept_invite(token: str, user: CurrentUser, session: SessionDep) -> Response:
    """Join the workspace. Only the account whose email was invited can accept (FR-18)."""
    await invites.accept_invite(session, user, token)
    return Response(status_code=204)
