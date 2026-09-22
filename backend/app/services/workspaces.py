from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, not_found
from app.core.permissions import Action, can_act_on_member
from app.models.document import DocumentGrant
from app.models.enums import WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import activity
from app.services.access import WorkspaceAccess


def _cannot_modify_owner() -> ApiError:
    return ApiError(403, "CANNOT_MODIFY_OWNER", "The workspace Owner can't be changed this way.")


async def list_workspaces(
    session: AsyncSession, user: User
) -> list[tuple[Workspace, WorkspaceRole]]:
    """Workspaces the user belongs to (guests included), excluding soft-deleted ones."""
    result = await session.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id, Workspace.deleted_at.is_(None))
        .order_by(Workspace.name, Workspace.id)
    )
    return [(workspace, role) for workspace, role in result.all()]


async def create_workspace(session: AsyncSession, user: User, name: str) -> Workspace:
    """A workspace and its Owner membership are created together, in one transaction."""
    workspace = Workspace(name=name, owner_id=user.id)
    session.add(workspace)
    await session.flush()  # assigns workspace.id
    session.add(
        WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER)
    )
    activity.record_activity(
        session,
        workspace_id=workspace.id,
        actor_id=user.id,
        action=activity.WORKSPACE_CREATED,
        target_type="workspace",
        target_id=workspace.id,
    )
    await session.commit()
    return workspace


async def soft_delete_workspace(session: AsyncSession, access: WorkspaceAccess) -> None:
    access.workspace.deleted_at = datetime.now(UTC)
    activity.record_activity(
        session,
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        action=activity.WORKSPACE_DELETED,
        target_type="workspace",
        target_id=access.workspace.id,
    )
    await session.commit()


async def list_members(
    session: AsyncSession, workspace_id: str
) -> list[tuple[WorkspaceMember, User, list[str] | None]]:
    """Members with their user details; guests also carry the document ids they were granted."""
    rows = (
        await session.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at, WorkspaceMember.id)
        )
    ).all()
    grants: dict[str, list[str]] = {}
    grant_rows = await session.execute(
        select(DocumentGrant.user_id, DocumentGrant.document_id)
        .where(DocumentGrant.workspace_id == workspace_id)
        .order_by(DocumentGrant.document_id)
    )
    for user_id, document_id in grant_rows.all():
        grants.setdefault(user_id, []).append(document_id)
    return [
        (member, user, grants.get(user.id, []) if member.role == WorkspaceRole.GUEST else None)
        for member, user in rows
    ]


async def _load_target_for_update(
    session: AsyncSession, workspace_id: str, user_id: str
) -> WorkspaceMember:
    """The target's membership, row-locked so a concurrent change cannot slip in between the
    checks below and our write. 404 if they are not a member of THIS workspace."""
    # populate_existing: the caller's own membership row is very likely already in this
    # session's identity map (get_workspace_access loaded it, unlocked, to authorize the
    # request) — without this, SQLAlchemy would hand back that stale cached object instead of
    # the row this FOR UPDATE just re-read, defeating the lock as a staleness check entirely.
    result = await session.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise not_found("Member not found.")
    return target


async def change_role(
    session: AsyncSession, access: WorkspaceAccess, target_user_id: str, new_role: WorkspaceRole
) -> None:
    target = await _load_target_for_update(session, access.workspace.id, target_user_id)
    if not can_act_on_member(access.role, target.role, Action.CHANGE_MEMBER_ROLE):
        raise _cannot_modify_owner()
    old_role = target.role
    if old_role == new_role:
        return
    target.role = new_role
    if old_role == WorkspaceRole.GUEST:
        # document grants only make sense for guests
        await session.execute(
            delete(DocumentGrant).where(
                DocumentGrant.workspace_id == access.workspace.id,
                DocumentGrant.user_id == target_user_id,
            )
        )
    activity.record_activity(
        session,
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        action=activity.MEMBER_ROLE_CHANGED,
        target_type="user",
        target_id=target_user_id,
        metadata={"from": old_role.value, "to": new_role.value},
    )
    await session.commit()


async def remove_member(
    session: AsyncSession, access: WorkspaceAccess, target_user_id: str
) -> None:
    target = await _load_target_for_update(session, access.workspace.id, target_user_id)
    if not can_act_on_member(access.role, target.role, Action.REMOVE_MEMBER):
        raise _cannot_modify_owner()
    removed_role = target.role
    # the row is the whole revocation: access is derived from it on every request, and the
    # composite FK cascades this user's document grants away in the same statement
    await session.delete(target)
    activity.record_activity(
        session,
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        action=activity.MEMBER_REMOVED,
        target_type="user",
        target_id=target_user_id,
        metadata={"role": removed_role.value},
    )
    await session.commit()


async def transfer_ownership(
    session: AsyncSession, access: WorkspaceAccess, target_user_id: str
) -> None:
    """Make an existing Admin the Owner and the current Owner an Admin, atomically.

    Exactly one Owner must exist at every commit. The database allows at most one (a partial
    unique index that is checked immediately), so the current Owner is demoted and flushed BEFORE
    the target is promoted.
    """
    # lock the workspace row: two concurrent transfers must not both succeed. populate_existing
    # matters here too — access.workspace was already loaded, unlocked, by get_workspace_access.
    workspace = (
        await session.execute(
            select(Workspace)
            .where(Workspace.id == access.workspace.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    caller = await _load_target_for_update(session, workspace.id, access.user.id)
    if caller.role != WorkspaceRole.OWNER:  # lost a race with another transfer
        raise ApiError(403, "FORBIDDEN", "You don't have permission to do that.")
    target = await _load_target_for_update(session, workspace.id, target_user_id)
    if target.role != WorkspaceRole.ADMIN:
        raise ApiError(
            409, "TARGET_MUST_BE_ADMIN", "Ownership can only be transferred to an existing Admin."
        )

    caller.role = WorkspaceRole.ADMIN
    await session.flush()  # the demotion must reach the database before the promotion
    target.role = WorkspaceRole.OWNER
    workspace.owner_id = target.user_id
    activity.record_activity(
        session,
        workspace_id=workspace.id,
        actor_id=access.user.id,
        action=activity.OWNERSHIP_TRANSFERRED,
        target_type="user",
        target_id=target_user_id,
        metadata={"from": access.user.id, "to": target_user_id},
    )
    await session.commit()
