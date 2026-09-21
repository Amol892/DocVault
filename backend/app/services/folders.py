from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, not_found
from app.models.document import Document
from app.models.enums import WorkspaceRole
from app.models.folder import Folder, FolderGrant
from app.models.workspace import WorkspaceMember
from app.services import activity
from app.services.access import (
    FolderAccess,
    WorkspaceAccess,
    get_live_folder,
    guest_visible_folder_ids,
)

MAX_FOLDER_DEPTH = 20  # nesting limit: keeps tree queries cheap and screens usable


def _name_taken() -> ApiError:
    return ApiError(409, "NAME_TAKEN", "A folder with this name already exists here.")


def _is_name_conflict(exc: IntegrityError) -> bool:
    return "uq_folders_sibling_name" in str(exc.orig)


async def list_folders(session: AsyncSession, access: WorkspaceAccess) -> list[Folder]:
    """Every live folder for Members and above; only granted folders (and their descendants) for
    a Guest."""
    statement = select(Folder).where(
        Folder.workspace_id == access.workspace.id, Folder.deleted_at.is_(None)
    )
    if access.role == WorkspaceRole.GUEST:
        visible = await guest_visible_folder_ids(session, access.workspace.id, access.user.id)
        statement = statement.where(Folder.id.in_(visible))
    result = await session.execute(statement.order_by(func.lower(Folder.name), Folder.id))
    return list(result.scalars())


async def _depth(session: AsyncSession, folder: Folder) -> int:
    """How many folders deep this one is (a root-level folder is 1)."""
    depth, node = 1, folder
    while node.parent_folder_id is not None and depth <= MAX_FOLDER_DEPTH:
        parent = await session.get(Folder, node.parent_folder_id)
        if parent is None:
            break
        node, depth = parent, depth + 1
    return depth


async def create_folder(
    session: AsyncSession, access: WorkspaceAccess, name: str, parent_folder_id: str | None
) -> Folder:
    if parent_folder_id is not None:
        parent = await get_live_folder(session, access.workspace.id, parent_folder_id)
        if parent is None:
            raise not_found("Parent folder not found.")
        if await _depth(session, parent) >= MAX_FOLDER_DEPTH:
            raise ApiError(
                422, "FOLDER_TOO_DEEP", f"Folders can be nested at most {MAX_FOLDER_DEPTH} levels."
            )
    folder = Folder(
        workspace_id=access.workspace.id,
        owner_id=access.user.id,
        parent_folder_id=parent_folder_id,
        name=name,
    )
    session.add(folder)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_name_conflict(exc):
            raise _name_taken() from exc
        raise
    return folder


async def rename_folder(session: AsyncSession, access: FolderAccess, name: str) -> Folder:
    access.folder.name = name
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_name_conflict(exc):
            raise _name_taken() from exc
        raise
    return access.folder


async def _free_name(
    session: AsyncSession, workspace_id: str, parent_id: str | None, name: str, exclude_id: str
) -> str:
    """`name`, or `name (moved 2)`... whichever is not already used by a live sibling."""
    candidate, attempt = name, 1
    while True:
        parent_filter = (
            Folder.parent_folder_id.is_(None)
            if parent_id is None
            else Folder.parent_folder_id == parent_id
        )
        taken = await session.execute(
            select(Folder.id).where(
                Folder.workspace_id == workspace_id,
                parent_filter,
                func.lower(Folder.name) == candidate.lower(),
                Folder.deleted_at.is_(None),
                Folder.id != exclude_id,
            )
        )
        if taken.first() is None:
            return candidate
        attempt += 1
        candidate = f"{name} (moved {attempt})"[:255]


async def delete_folder(session: AsyncSession, access: FolderAccess) -> None:
    """Soft delete. Nothing inside is lost or hidden (FR-23): sub-folders and documents move up to
    the deleted folder's parent (or the root). Guest grants on the folder itself are removed."""
    folder = access.folder
    workspace_id = folder.workspace_id
    if workspace_id is None:  # personal folders do not exist
        raise not_found("Folder not found.")
    parent_id = folder.parent_folder_id

    folder.deleted_at = datetime.now(UTC)
    await session.flush()  # a deleted folder no longer counts as a name clash

    children = (
        (
            await session.execute(
                select(Folder)
                .where(Folder.parent_folder_id == folder.id, Folder.deleted_at.is_(None))
                .order_by(Folder.id)
            )
        )
        .scalars()
        .all()
    )
    for child in children:
        child.name = await _free_name(session, workspace_id, parent_id, child.name, child.id)
        child.parent_folder_id = parent_id
        await session.flush()
    await session.execute(
        update(Document).where(Document.folder_id == folder.id).values(folder_id=parent_id)
    )
    await session.execute(delete(FolderGrant).where(FolderGrant.folder_id == folder.id))
    await session.commit()


async def grant_access(session: AsyncSession, access: FolderAccess, target_user_id: str) -> None:
    """Give a Guest access to this folder and everything under it. Idempotent."""
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
        raise ApiError(409, "NOT_A_GUEST", "Only guests are given access to individual folders.")

    existing = await session.execute(
        select(FolderGrant.id).where(
            FolderGrant.folder_id == access.folder.id, FolderGrant.user_id == target_user_id
        )
    )
    if existing.first() is not None:
        return
    session.add(
        FolderGrant(
            workspace_id=workspace_id,
            folder_id=access.folder.id,
            user_id=target_user_id,
            granted_by=access.workspace.user.id,
        )
    )
    activity.record_activity(
        session,
        workspace_id=workspace_id,
        actor_id=access.workspace.user.id,
        action=activity.GUEST_FOLDER_GRANTED,
        target_type="user",
        target_id=target_user_id,
        metadata={"folder_id": access.folder.id},
    )
    await session.commit()


async def revoke_access(session: AsyncSession, access: FolderAccess, target_user_id: str) -> None:
    """Take a Guest's access to this folder away, effective on their next request. Idempotent."""
    result = await session.execute(
        delete(FolderGrant).where(
            FolderGrant.folder_id == access.folder.id, FolderGrant.user_id == target_user_id
        )
    )
    if result.rowcount:  # type: ignore[attr-defined]
        activity.record_activity(
            session,
            workspace_id=access.workspace.workspace.id,
            actor_id=access.workspace.user.id,
            action=activity.GUEST_FOLDER_REVOKED,
            target_type="user",
            target_id=target_user_id,
            metadata={"folder_id": access.folder.id},
        )
    await session.commit()
