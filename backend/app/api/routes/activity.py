from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require
from app.core.permissions import Action
from app.schemas.activity import ActivityLogOut
from app.schemas.common import ErrorResponse, Paginated, Responses
from app.services import activity
from app.services.access import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}/activity", tags=["activity"])

_RESPONSES: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"},
    403: {"model": ErrorResponse, "description": "Only Admins and Owners can view the activity"},
    404: {"model": ErrorResponse, "description": "No such workspace, or you are not a member"},
}


@router.get("", response_model=Paginated[ActivityLogOut], responses=_RESPONSES)
async def list_activity(
    access: Annotated[WorkspaceAccess, Depends(require(Action.VIEW_ACTIVITY_LOG))],
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
) -> Paginated[ActivityLogOut]:
    """The workspace's audit trail (FR-29, FR-30), newest first."""
    rows, total = await activity.list_activity(session, access.workspace.id, page)
    return Paginated[ActivityLogOut](
        items=[
            ActivityLogOut(
                id=entry.id,
                actor_id=entry.actor_id,
                actor_name=name,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                metadata=entry.metadata_,
                created_at=entry.created_at,
            )
            for entry, name in rows
        ],
        page=page,
        total=total,
    )
