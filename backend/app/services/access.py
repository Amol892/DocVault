"""Who may see what. The loaders behind api/deps.py: they answer "what is this user's standing
here?" and return None for every kind of "no", so a caller can never tell a missing thing from one
they are not allowed to know about.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.enums import WorkspaceRole
from app.models.folder import Folder, FolderGrant
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


@dataclass(frozen=True)
class WorkspaceAccess:
    """The caller's standing in one workspace."""

    workspace: Workspace
    membership: WorkspaceMember
    user: User

    @property
    def role(self) -> WorkspaceRole:
        return self.membership.role


@dataclass(frozen=True)
class FolderAccess:
    folder: Folder
    workspace: WorkspaceAccess

    @property
    def role(self) -> WorkspaceRole:
        return self.workspace.role


@dataclass(frozen=True)
class DocumentAccess:
    """The caller's standing for one document. `workspace` is None for a personal document, whose
    owner may do everything to it and nobody else can even see it."""

    document: Document
    user: User
    workspace: WorkspaceAccess | None

    @property
    def role(self) -> WorkspaceRole:
        return self.workspace.role if self.workspace else WorkspaceRole.OWNER


@dataclass(frozen=True)
class UploadTarget:
    """Where an authorized upload lands: a new document (in a workspace folder or personal) or a
    new version of `document`."""

    user: User
    workspace: WorkspaceAccess | None
    folder_id: str | None
    document: Document | None


@dataclass(frozen=True)
class ListScope:
    """What a document listing covers: the caller's personal documents (`workspace` None) or a
    workspace, optionally narrowed to one folder."""

    user: User
    workspace: WorkspaceAccess | None
    folder_id: str | None


async def load_workspace_access(
    session: AsyncSession, user: User, workspace_id: str
) -> WorkspaceAccess | None:
    """None if the workspace is missing, soft-deleted, or the user is not a member."""
    result = await session.execute(
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            Workspace.id == workspace_id,
            Workspace.deleted_at.is_(None),
            WorkspaceMember.user_id == user.id,
        )
    )
    row = result.first()
    if row is None:
        return None
    workspace, membership = row
    return WorkspaceAccess(workspace=workspace, membership=membership, user=user)


async def guest_visible_folder_ids(
    session: AsyncSession, workspace_id: str, user_id: str
) -> set[str]:
    """The folders a Guest may see: every folder they were granted, and all its descendants."""
    granted = (
        select(Folder.id)
        .join(FolderGrant, FolderGrant.folder_id == Folder.id)
        .where(
            FolderGrant.workspace_id == workspace_id,
            FolderGrant.user_id == user_id,
            Folder.deleted_at.is_(None),
        )
        .cte("visible_folders", recursive=True)
    )
    descendants = (
        select(Folder.id)
        .join(granted, Folder.parent_folder_id == granted.c.id)
        .where(Folder.deleted_at.is_(None))
    )
    tree = granted.union(descendants)
    result = await session.execute(select(tree.c.id))
    return set(result.scalars())


async def can_see_folder(
    session: AsyncSession, access: WorkspaceAccess, folder_id: str | None
) -> bool:
    """Members and above see every folder; a Guest only granted ones (and never the root)."""
    if access.role != WorkspaceRole.GUEST:
        return True
    if folder_id is None:
        return False
    visible = await guest_visible_folder_ids(session, access.workspace.id, access.user.id)
    return folder_id in visible


async def get_live_folder(
    session: AsyncSession, workspace_id: str, folder_id: str
) -> Folder | None:
    result = await session.execute(
        select(Folder).where(
            Folder.id == folder_id,
            Folder.workspace_id == workspace_id,
            Folder.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def load_folder_access(
    session: AsyncSession, user: User, folder_id: str
) -> FolderAccess | None:
    folder = (
        await session.execute(
            select(Folder).where(Folder.id == folder_id, Folder.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if folder is None or folder.workspace_id is None:  # there are no personal folders
        return None
    workspace = await load_workspace_access(session, user, folder.workspace_id)
    if workspace is None or not await can_see_folder(session, workspace, folder.id):
        return None
    return FolderAccess(folder=folder, workspace=workspace)


async def load_document_access(
    session: AsyncSession, user: User, document_id: str
) -> DocumentAccess | None:
    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if document is None:
        return None
    if document.workspace_id is None:  # personal: the owner and nobody else
        if document.owner_id != user.id:
            return None
        return DocumentAccess(document=document, user=user, workspace=None)
    workspace = await load_workspace_access(session, user, document.workspace_id)
    if workspace is None or not await can_see_folder(session, workspace, document.folder_id):
        return None
    return DocumentAccess(document=document, user=user, workspace=workspace)
