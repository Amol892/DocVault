from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from app.models.user import User

# Action names recorded in activity_logs (FR-29); see the catalogue in PRD/04-database-schema.md
WORKSPACE_CREATED = "workspace.created"
WORKSPACE_DELETED = "workspace.deleted"
MEMBER_ROLE_CHANGED = "member.role_changed"
MEMBER_REMOVED = "member.removed"
OWNERSHIP_TRANSFERRED = "ownership.transferred"
GUEST_DOCUMENT_GRANTED = "guest.document_granted"
GUEST_DOCUMENT_REVOKED = "guest.document_revoked"
MEMBER_INVITED = "member.invited"
MEMBER_JOINED = "member.joined"
INVITE_REVOKED = "invite.revoked"
SHARE_LINK_CREATED = "share_link.created"
SHARE_LINK_UPDATED = "share_link.updated"
SHARE_LINK_REVOKED = "share_link.revoked"


def record_activity(
    session: AsyncSession,
    *,
    workspace_id: str | None,
    actor_id: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Queue an audit entry in the caller's transaction, so it commits or rolls back with the
    change it describes."""
    session.add(
        ActivityLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_=metadata or {},
        )
    )


async def list_activity(
    session: AsyncSession, workspace_id: str, page: int, page_size: int = 50
) -> tuple[list[tuple[ActivityLog, str]], int]:
    """One page of a workspace's audit trail, newest first, with each actor's name."""
    total = (
        await session.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(ActivityLog.workspace_id == workspace_id)
        )
    ).scalar_one()
    rows = await session.execute(
        select(ActivityLog, User.name)
        .join(User, User.id == ActivityLog.actor_id)
        .where(ActivityLog.workspace_id == workspace_id)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return [(entry, name) for entry, name in rows.all()], total
