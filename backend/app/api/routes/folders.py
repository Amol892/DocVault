from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import SessionDep, get_workspace_access, require, require_folder
from app.core.permissions import Action
from app.models.folder import Folder
from app.schemas.common import ErrorResponse, Responses
from app.schemas.folder import FolderCreate, FolderOut, FolderPatch
from app.services import folders
from app.services.access import FolderAccess, WorkspaceAccess

router = APIRouter(tags=["folders"])

_RESPONSES: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"},
    403: {"model": ErrorResponse, "description": "Your role does not allow this"},
    404: {"model": ErrorResponse, "description": "No such folder or workspace, or no access"},
    409: {"model": ErrorResponse, "description": "A folder with this name already exists here"},
}


def _out(folder: Folder) -> FolderOut:
    return FolderOut(
        id=folder.id,
        workspace_id=folder.workspace_id,
        parent_folder_id=folder.parent_folder_id,
        name=folder.name,
    )


@router.get(
    "/workspaces/{workspace_id}/folders", response_model=list[FolderOut], responses=_RESPONSES
)
async def list_folders(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_access)], session: SessionDep
) -> list[FolderOut]:
    """Every folder for Members and above; only granted folders (and their subfolders) for a
    Guest."""
    return [_out(folder) for folder in await folders.list_folders(session, access)]


@router.post(
    "/workspaces/{workspace_id}/folders",
    status_code=201,
    response_model=FolderOut,
    responses=_RESPONSES,
)
async def create_folder(
    body: FolderCreate,
    access: Annotated[WorkspaceAccess, Depends(require(Action.CREATE_FOLDER))],
    session: SessionDep,
) -> FolderOut:
    folder = await folders.create_folder(session, access, body.name, body.parent_folder_id)
    return _out(folder)


@router.patch("/folders/{folder_id}", response_model=FolderOut, responses=_RESPONSES)
async def rename_folder(
    body: FolderPatch,
    access: Annotated[FolderAccess, Depends(require_folder(Action.CREATE_FOLDER))],
    session: SessionDep,
) -> FolderOut:
    """Rename (`name`) or move (`parent_folder_id`, null = root); exactly one per request."""
    if "name" in body.model_fields_set:
        return _out(await folders.rename_folder(session, access, str(body.name)))
    return _out(await folders.move_folder(session, access, body.parent_folder_id))


@router.delete("/folders/{folder_id}", status_code=204, responses=_RESPONSES)
async def delete_folder(
    access: Annotated[FolderAccess, Depends(require_folder(Action.CREATE_FOLDER))],
    session: SessionDep,
) -> Response:
    """Soft delete. Sub-folders and documents move up a level; nothing inside is lost (FR-23)."""
    await folders.delete_folder(session, access)
    return Response(status_code=204)
