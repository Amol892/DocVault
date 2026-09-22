"""Authentication and authorization dependencies.

This module is the ONLY place role/membership checks live. Routes must depend on
what is defined here and never re-implement checks. See PRD/06-permission-matrix.md.

Every request touching a workspace goes through get_workspace_access():
  1. the JWT identifies the user (and is not revoked, and the user is still active);
  2. a workspace_members row must exist for (workspace, user), on a live workspace;
  3. require(action) compares the role with the matrix.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, forbidden, not_found, unauthorized
from app.core.permissions import Action, can
from app.core.security import InvalidTokenError, TokenClaims, decode_access_token
from app.db.session import get_session
from app.models.enums import WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.document import UploadUrlRequest
from app.services.access import (
    DocumentAccess,
    FolderAccess,
    ListScope,
    ShareLinkAccess,
    UploadTarget,
    WorkspaceAccess,
    get_live_folder,
    load_document_access,
    load_folder_access,
    load_share_link_access,
    load_trashed_document_access,
    load_workspace_access,
)
from app.services.accounts import is_token_revoked

# auto_error=False so a missing header becomes our own 401 in the standard error shape
_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: SessionDep,
) -> TokenClaims:
    """A valid, unexpired, non-revoked token. Every failure is the same 401."""
    if credentials is None:
        raise unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise unauthorized() from None
    if await is_token_revoked(session, claims.jti):
        raise unauthorized()
    return claims


async def get_current_user_unverified(
    claims: Annotated[TokenClaims, Depends(get_current_claims)],
    session: SessionDep,
) -> User:
    """The signed-in user, even if they have not confirmed their email yet. Only the account
    endpoints (/auth/me, resend-verification) use this; everything else needs a verified user."""
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


async def get_current_user(
    user: Annotated[User, Depends(get_current_user_unverified)],
) -> User:
    """FR-1: a signed-in user with a confirmed email address."""
    if not user.email_verified:
        raise ApiError(403, "EMAIL_NOT_VERIFIED", "Confirm your email address to continue.")
    return user


CurrentClaims = Annotated[TokenClaims, Depends(get_current_claims)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AnyUser = Annotated[User, Depends(get_current_user_unverified)]


async def get_workspace_access(
    workspace_id: str, user: CurrentUser, session: SessionDep
) -> WorkspaceAccess:
    """The caller's membership in this workspace.

    404 whether the workspace does not exist, was deleted, or the caller is not a member: a
    non-member must not be able to tell those apart (no leaking which workspaces exist).
    """
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
        raise not_found("Workspace not found.")
    workspace, membership = row
    return WorkspaceAccess(workspace=workspace, membership=membership, user=user)


def require(action: Action) -> Callable[..., Awaitable[WorkspaceAccess]]:
    """Dependency factory: the caller must be a member whose role allows `action` (403 if not)."""

    async def dependency(
        access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
    ) -> WorkspaceAccess:
        if not can(access.role, action):
            raise forbidden()
        return access

    return dependency


async def get_folder_access(folder_id: str, user: CurrentUser, session: SessionDep) -> FolderAccess:
    """404 for a missing or deleted folder, one in a workspace the caller is not in, and (for a
    Guest) one they were not granted: all indistinguishable."""
    access = await load_folder_access(session, user, folder_id)
    if access is None:
        raise not_found("Folder not found.")
    return access


def require_folder(action: Action) -> Callable[..., Awaitable[FolderAccess]]:
    async def dependency(
        access: Annotated[FolderAccess, Depends(get_folder_access)],
    ) -> FolderAccess:
        if not can(access.role, action):
            raise forbidden()
        return access

    return dependency


async def get_document_access(
    document_id: str, user: CurrentUser, session: SessionDep
) -> DocumentAccess:
    """404 for a missing or deleted document, another user's personal document, one in a workspace
    the caller is not in, and (for a Guest) one in a folder they were not granted."""
    access = await load_document_access(session, user, document_id)
    if access is None:
        raise not_found("Document not found.")
    return access


def require_document(action: Action) -> Callable[..., Awaitable[DocumentAccess]]:
    """The owner of a personal document may do anything to it; otherwise the workspace role must
    allow `action`."""

    async def dependency(
        access: Annotated[DocumentAccess, Depends(get_document_access)],
    ) -> DocumentAccess:
        if not can(access.role, action):
            raise forbidden()
        return access

    return dependency


async def get_upload_target(
    body: UploadUrlRequest, user: CurrentUser, session: SessionDep
) -> UploadTarget:
    """Who may upload where. A new version needs the same right as a new document."""
    if body.document_id is not None:
        existing = await load_document_access(session, user, body.document_id)
        if existing is None:
            raise not_found("Document not found.")
        if not can(existing.role, Action.UPLOAD_DOCUMENT):
            raise forbidden()
        return UploadTarget(
            user=user,
            workspace=existing.workspace,
            folder_id=existing.document.folder_id,
            document=existing.document,
        )
    if body.workspace_id is None:  # a personal document; there are no personal folders
        if body.folder_id is not None:
            raise not_found("Folder not found.")
        return UploadTarget(user=user, workspace=None, folder_id=None, document=None)
    workspace = await load_workspace_access(session, user, body.workspace_id)
    if workspace is None:
        raise not_found("Workspace not found.")
    if not can(workspace.role, Action.UPLOAD_DOCUMENT):
        raise forbidden()
    if (
        body.folder_id is not None
        and await get_live_folder(session, workspace.workspace.id, body.folder_id) is None
    ):
        raise not_found("Folder not found.")
    return UploadTarget(user=user, workspace=workspace, folder_id=body.folder_id, document=None)


async def get_list_scope(
    user: CurrentUser,
    session: SessionDep,
    workspace_id: Annotated[str | None, Query()] = None,
    folder_id: Annotated[str | None, Query()] = None,
) -> ListScope:
    """No workspace = the caller's own personal documents. Otherwise membership is required. A
    Guest never browses folders (FR-21): any `folder_id` they send is ignored and they always get
    their flat set of individually granted documents. For Members and above, a named folder must
    exist."""
    if workspace_id is None:
        if folder_id is not None:
            raise not_found("Folder not found.")
        return ListScope(user=user, workspace=None, folder_id=None)
    workspace = await load_workspace_access(session, user, workspace_id)
    if workspace is None:
        raise not_found("Workspace not found.")
    if workspace.role == WorkspaceRole.GUEST:
        return ListScope(user=user, workspace=workspace, folder_id=None)
    if (
        folder_id is not None
        and await get_live_folder(session, workspace.workspace.id, folder_id) is None
    ):
        raise not_found("Folder not found.")
    return ListScope(user=user, workspace=workspace, folder_id=folder_id)


async def get_trashed_document_access(
    document_id: str, user: CurrentUser, session: SessionDep
) -> DocumentAccess:
    """A soft-deleted document the caller could restore; 404 for anything else."""
    access = await load_trashed_document_access(session, user, document_id)
    if access is None:
        raise not_found("Document not found.")
    if not can(access.role, Action.UPLOAD_DOCUMENT):
        raise forbidden()
    return access


async def get_trash_scope(scope: Annotated[ListScope, Depends(get_list_scope)]) -> ListScope:
    """Who may look at the trash: the owner of personal documents, Members and above in a
    workspace (never Guests)."""
    if scope.workspace is not None and not can(scope.workspace.role, Action.UPLOAD_DOCUMENT):
        raise forbidden()
    return scope


async def get_share_link_access(
    link_id: str, user: CurrentUser, session: SessionDep
) -> ShareLinkAccess:
    """A share link the caller may manage: 404 unless they can see its document, 403 unless their
    role may share (Members and above; never Guests)."""
    access = await load_share_link_access(session, user, link_id)
    if access is None:
        raise not_found("Share link not found.")
    if not can(access.document.role, Action.CREATE_SHARE_LINK):
        raise forbidden()
    return access
