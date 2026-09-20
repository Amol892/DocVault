from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, SessionDep, get_workspace_access, require
from app.core.permissions import Action
from app.models.enums import WorkspaceRole
from app.schemas.common import ErrorResponse, Responses
from app.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceSummaryOut
from app.services import workspaces
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

_RESPONSES: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"},
    404: {"model": ErrorResponse, "description": "No such workspace, or you are not a member"},
}


def _out(access: WorkspaceAccess) -> WorkspaceOut:
    return WorkspaceOut(
        id=access.workspace.id,
        name=access.workspace.name,
        owner_id=access.workspace.owner_id,
        created_at=access.workspace.created_at,
        my_role=access.role,
    )


@router.get("", response_model=list[WorkspaceSummaryOut], responses={401: _RESPONSES[401]})
async def list_workspaces(user: CurrentUser, session: SessionDep) -> list[WorkspaceSummaryOut]:
    """Only workspaces the caller belongs to (FR-17); nothing else is visible or discoverable."""
    rows = await workspaces.list_workspaces(session, user)
    return [WorkspaceSummaryOut(id=ws.id, name=ws.name, role=role) for ws, role in rows]


@router.post("", status_code=201, response_model=WorkspaceOut, responses={401: _RESPONSES[401]})
async def create_workspace(
    body: WorkspaceCreate, user: CurrentUser, session: SessionDep
) -> WorkspaceOut:
    """Any signed-in user can create a workspace and becomes its Owner (FR-16)."""
    workspace = await workspaces.create_workspace(session, user, body.name)
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        owner_id=workspace.owner_id,
        created_at=workspace.created_at,
        my_role=WorkspaceRole.OWNER,
    )


@router.get("/{workspace_id}", response_model=WorkspaceOut, responses=_RESPONSES)
async def get_workspace(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
) -> WorkspaceOut:
    return _out(access)


@router.delete("/{workspace_id}", status_code=204, responses=_RESPONSES)
async def delete_workspace(
    access: Annotated[WorkspaceAccess, Depends(require(Action.DELETE_WORKSPACE))],
    session: SessionDep,
) -> Response:
    """Owner only. A soft delete: the workspace disappears for everyone but its rows are kept."""
    await workspaces.soft_delete_workspace(session, access)
    return Response(status_code=204)
