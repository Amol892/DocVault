from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import SessionDep, require
from app.core.permissions import Action
from app.schemas.common import ErrorResponse, Responses
from app.schemas.workspace import MemberOut, RoleChange
from app.services import workspaces
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}/members", tags=["members"])

_RESPONSES: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"},
    403: {"model": ErrorResponse, "description": "Your role does not allow this"},
    404: {"model": ErrorResponse, "description": "No such workspace or member"},
}


@router.get("", response_model=list[MemberOut], responses=_RESPONSES)
async def list_members(
    access: Annotated[WorkspaceAccess, Depends(require(Action.SEE_MEMBER_LIST))],
    session: SessionDep,
) -> list[MemberOut]:
    rows = await workspaces.list_members(session, access.workspace.id)
    return [
        MemberOut(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=member.role,
            joined_at=member.created_at,
            granted_folder_ids=granted,
        )
        for member, user, granted in rows
    ]


@router.patch("/{user_id}", status_code=204, responses=_RESPONSES)
async def change_member_role(
    user_id: str,
    body: RoleChange,
    access: Annotated[WorkspaceAccess, Depends(require(Action.CHANGE_MEMBER_ROLE))],
    session: SessionDep,
) -> Response:
    """Admin+; never the Owner, and never to Owner (that is transfer-ownership)."""
    await workspaces.change_role(session, access, user_id, body.role)
    return Response(status_code=204)


@router.delete("/{user_id}", status_code=204, responses=_RESPONSES)
async def remove_member(
    user_id: str,
    access: Annotated[WorkspaceAccess, Depends(require(Action.REMOVE_MEMBER))],
    session: SessionDep,
) -> Response:
    """Admin+; never the Owner. Their access ends on their very next request (FR-19)."""
    await workspaces.remove_member(session, access, user_id)
    return Response(status_code=204)


@router.post("/{user_id}/transfer-ownership", status_code=204, responses=_RESPONSES)
async def transfer_ownership(
    user_id: str,
    access: Annotated[WorkspaceAccess, Depends(require(Action.TRANSFER_OWNERSHIP))],
    session: SessionDep,
) -> Response:
    """Owner only, and only to an existing Admin; the Owner becomes an Admin (FR-20)."""
    await workspaces.transfer_ownership(session, access, user_id)
    return Response(status_code=204)
