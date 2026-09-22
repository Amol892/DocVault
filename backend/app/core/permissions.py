"""The permission matrix (PRD/06-permission-matrix.md) as data.

This is the single backend source of truth. The numbers must equal the frontend's
ACTION_LEVEL in frontend/src/permissions/roleHierarchy.ts (tests/test_permissions.py checks it).
The frontend copy only hides controls; every request is checked here, in api/deps.py.
"""

from enum import StrEnum

from app.models.enums import WorkspaceRole

ROLE_LEVEL: dict[WorkspaceRole, int] = {
    WorkspaceRole.OWNER: 4,
    WorkspaceRole.ADMIN: 3,
    WorkspaceRole.MEMBER: 2,
    WorkspaceRole.GUEST: 1,
}


class Action(StrEnum):
    VIEW_GRANTED_DOCS = "VIEW_GRANTED_DOCS"
    UPLOAD_DOCUMENT = "UPLOAD_DOCUMENT"
    CREATE_FOLDER = "CREATE_FOLDER"
    CREATE_SHARE_LINK = "CREATE_SHARE_LINK"
    SEE_MEMBER_LIST = "SEE_MEMBER_LIST"
    INVITE_MEMBER = "INVITE_MEMBER"
    CHANGE_MEMBER_ROLE = "CHANGE_MEMBER_ROLE"
    REMOVE_MEMBER = "REMOVE_MEMBER"
    GRANT_DOCUMENT_ACCESS = "GRANT_DOCUMENT_ACCESS"
    VIEW_ACTIVITY_LOG = "VIEW_ACTIVITY_LOG"
    TRANSFER_OWNERSHIP = "TRANSFER_OWNERSHIP"
    DELETE_WORKSPACE = "DELETE_WORKSPACE"


# Minimum role level needed for each action.
ACTION_LEVEL: dict[Action, int] = {
    Action.VIEW_GRANTED_DOCS: 1,  # guest+ (still needs the document-grant check separately)
    Action.UPLOAD_DOCUMENT: 2,
    Action.CREATE_FOLDER: 2,
    Action.CREATE_SHARE_LINK: 2,
    Action.SEE_MEMBER_LIST: 2,
    Action.INVITE_MEMBER: 3,
    Action.CHANGE_MEMBER_ROLE: 3,  # admin+, but never on the Owner (see can_act_on_member)
    Action.REMOVE_MEMBER: 3,  # admin+, but never on the Owner
    Action.GRANT_DOCUMENT_ACCESS: 3,
    Action.VIEW_ACTIVITY_LOG: 3,
    Action.TRANSFER_OWNERSHIP: 4,  # owner only
    Action.DELETE_WORKSPACE: 4,  # owner only
}


def can(role: WorkspaceRole, action: Action) -> bool:
    return ROLE_LEVEL[role] >= ACTION_LEVEL[action]


def can_act_on_member(
    actor_role: WorkspaceRole, target_role: WorkspaceRole, action: Action
) -> bool:
    """An Admin passes the level check but must still never touch the Owner; ownership only
    moves through the explicit transfer action."""
    if target_role == WorkspaceRole.OWNER:
        return False
    return can(actor_role, action)
