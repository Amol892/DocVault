"""Who may see what. The loaders behind api/deps.py: they answer "what is this user's standing
here?" and return None for every kind of "no", so a caller can never tell a missing thing from one
they are not allowed to know about.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentGrant
from app.models.enums import WorkspaceRole
from app.models.folder import Folder
from app.models.share_link import ShareLink
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
    workspace, optionally narrowed to one folder. For a Guest, `folder_id` is always None: Guests
    never browse folders, they always get their flat set of individually granted documents
    (FR-21)."""

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


async def guest_visible_document_ids(
    session: AsyncSession, workspace_id: str, user_id: str
) -> set[str]:
    """The documents a Guest may see: exactly the ones individually granted to them (FR-21). Flat
    by design — a document grant carries no folder hierarchy."""
    result = await session.execute(
        select(DocumentGrant.document_id).where(
            DocumentGrant.workspace_id == workspace_id, DocumentGrant.user_id == user_id
        )
    )
    return set(result.scalars())


async def _is_document_granted(session: AsyncSession, document_id: str, user_id: str) -> bool:
    result = await session.execute(
        select(DocumentGrant.id).where(
            DocumentGrant.document_id == document_id, DocumentGrant.user_id == user_id
        )
    )
    return result.first() is not None


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


async def get_live_document(
    session: AsyncSession, workspace_id: str, document_id: str
) -> Document | None:
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def load_folder_access(
    session: AsyncSession, user: User, folder_id: str
) -> FolderAccess | None:
    """Folders are a Member-and-above concept: a Guest never has standing on any folder, since
    Guest access is granted per document, not per folder (FR-21)."""
    folder = (
        await session.execute(
            select(Folder).where(Folder.id == folder_id, Folder.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if folder is None or folder.workspace_id is None:  # there are no personal folders
        return None
    workspace = await load_workspace_access(session, user, folder.workspace_id)
    if workspace is None or workspace.role == WorkspaceRole.GUEST:
        return None
    return FolderAccess(folder=folder, workspace=workspace)


async def _load_document_access(
    session: AsyncSession, user: User, document_id: str, *, deleted: bool
) -> DocumentAccess | None:
    condition = Document.deleted_at.is_not(None) if deleted else Document.deleted_at.is_(None)
    document = (
        await session.execute(select(Document).where(Document.id == document_id, condition))
    ).scalar_one_or_none()
    if document is None:
        return None
    if document.workspace_id is None:  # personal: the owner and nobody else
        if document.owner_id != user.id:
            return None
        return DocumentAccess(document=document, user=user, workspace=None)
    workspace = await load_workspace_access(session, user, document.workspace_id)
    if workspace is None:
        return None
    if workspace.role == WorkspaceRole.GUEST and not await _is_document_granted(
        session, document.id, user.id
    ):
        return None
    return DocumentAccess(document=document, user=user, workspace=workspace)


async def load_document_access(
    session: AsyncSession, user: User, document_id: str
) -> DocumentAccess | None:
    """A live document the user may see."""
    return await _load_document_access(session, user, document_id, deleted=False)


async def load_trashed_document_access(
    session: AsyncSession, user: User, document_id: str
) -> DocumentAccess | None:
    """A soft-deleted document, for restoring it. Same visibility rules as a live one."""
    return await _load_document_access(session, user, document_id, deleted=True)


@dataclass(frozen=True)
class ShareLinkAccess:
    """A share link together with the caller's standing for its document."""

    link: ShareLink
    document: DocumentAccess


async def load_share_link_access(
    session: AsyncSession, user: User, link_id: str
) -> ShareLinkAccess | None:
    link = await session.get(ShareLink, link_id)
    if link is None:
        return None
    document = await load_document_access(session, user, link.document_id)
    if document is None:
        return None
    return ShareLinkAccess(link=link, document=document)
