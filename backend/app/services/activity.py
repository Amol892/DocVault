from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog

# Action names recorded in activity_logs (FR-29); see the catalogue in PRD/04-database-schema.md
WORKSPACE_CREATED = "workspace.created"
WORKSPACE_DELETED = "workspace.deleted"
MEMBER_ROLE_CHANGED = "member.role_changed"
MEMBER_REMOVED = "member.removed"
OWNERSHIP_TRANSFERRED = "ownership.transferred"
GUEST_FOLDER_GRANTED = "guest.folder_granted"
GUEST_FOLDER_REVOKED = "guest.folder_revoked"


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
