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

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, not_found, unauthorized
from app.core.permissions import Action, can
from app.core.security import InvalidTokenError, TokenClaims, decode_access_token
from app.db.session import get_session
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.accounts import is_token_revoked
from app.services.workspaces import WorkspaceAccess

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


async def get_current_user(
    claims: Annotated[TokenClaims, Depends(get_current_claims)],
    session: SessionDep,
) -> User:
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


CurrentClaims = Annotated[TokenClaims, Depends(get_current_claims)]
CurrentUser = Annotated[User, Depends(get_current_user)]


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
