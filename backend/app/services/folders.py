from datetime import UTC, datetime

from sqlalchemy import delete, func, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, not_found
from app.models.document import Document, DocumentGrant
from app.models.enums import WorkspaceRole
from app.models.folder import Folder
from app.services.access import FolderAccess, WorkspaceAccess, get_live_folder

MAX_FOLDER_DEPTH = 20  # nesting limit: keeps tree queries cheap and screens usable


def _name_taken() -> ApiError:
    return ApiError(409, "NAME_TAKEN", "A folder with this name already exists here.")


def _is_name_conflict(exc: IntegrityError) -> bool:
    return "uq_folders_sibling_name" in str(exc.orig)


async def list_folders(session: AsyncSession, access: WorkspaceAccess) -> list[Folder]:
    """Every live folder for Members and above. A Guest never browses folders (FR-21): access is
    granted per document, so this is always empty for them."""
    if access.role == WorkspaceRole.GUEST:
        return []
    statement = select(Folder).where(
        Folder.workspace_id == access.workspace.id, Folder.deleted_at.is_(None)
    )
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
    the deleted folder's parent (or the root). Documents that move this way have any Guest grants
    on them revoked: grants are folder-pinned (FR-21), and this folder is going away."""
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

    moved_document_ids = list(
        (
            await session.execute(select(Document.id).where(Document.folder_id == folder.id))
        ).scalars()
    )
    await session.execute(
        update(Document).where(Document.folder_id == folder.id).values(folder_id=parent_id)
    )
    if moved_document_ids:
        await session.execute(
            delete(DocumentGrant).where(DocumentGrant.document_id.in_(moved_document_ids))
        )
    await session.commit()


async def _subtree_height(session: AsyncSession, folder_id: str) -> int:
    """Levels in the tree rooted at this folder, itself included (a leaf is 1)."""
    tree = (
        select(Folder.id.label("id"), literal(1).label("level"))
        .where(Folder.id == folder_id)
        .cte("subtree", recursive=True)
    )
    children = (
        select(Folder.id, tree.c.level + 1)
        .join(tree, Folder.parent_folder_id == tree.c.id)
        .where(Folder.deleted_at.is_(None))
    )
    tree = tree.union_all(children)
    return int((await session.execute(select(func.max(tree.c.level)))).scalar_one())


async def _is_inside(session: AsyncSession, folder_id: str, ancestor_id: str) -> bool:
    """True if `folder_id` is `ancestor_id` or lies anywhere below it."""
    node: str | None = folder_id
    for _ in range(MAX_FOLDER_DEPTH + 1):
        if node is None:
            return False
        if node == ancestor_id:
            return True
        parent = await session.get(Folder, node)
        node = parent.parent_folder_id if parent else None
    return False


async def move_folder(
    session: AsyncSession, access: FolderAccess, parent_folder_id: str | None
) -> Folder:
    """Move a folder, with everything in it, under another folder (or to the workspace root).
    Documents inside keep their folder_id (they are still directly in this same folder), so any
    Guest grants on them are unaffected — grants are pinned to a document's immediate folder, not
    to its position in the tree."""
    folder = access.folder
    workspace_id = access.workspace.workspace.id
    if parent_folder_id is not None:
        parent = await get_live_folder(session, workspace_id, parent_folder_id)
        if parent is None:
            raise not_found("Target folder not found.")
        if await _is_inside(session, parent.id, folder.id):
            raise ApiError(422, "FOLDER_CYCLE", "A folder can't be moved into itself.")
        if await _depth(session, parent) + await _subtree_height(session, folder.id) > (
            MAX_FOLDER_DEPTH
        ):
            raise ApiError(
                422, "FOLDER_TOO_DEEP", f"Folders can be nested at most {MAX_FOLDER_DEPTH} levels."
            )
    folder.parent_folder_id = parent_folder_id
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_name_conflict(exc):
            raise _name_taken() from exc
        raise
    return folder
