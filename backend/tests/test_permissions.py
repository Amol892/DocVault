"""The permission matrix (PRD/06) and its agreement with the frontend copy. No database needed."""

import re

import pytest

from app.config import ROOT_DIR
from app.core.permissions import ACTION_LEVEL, ROLE_LEVEL, Action, can, can_act_on_member
from app.models.enums import WorkspaceRole

OWNER, ADMIN, MEMBER, GUEST = (
    WorkspaceRole.OWNER,
    WorkspaceRole.ADMIN,
    WorkspaceRole.MEMBER,
    WorkspaceRole.GUEST,
)

# PRD/06-permission-matrix.md, row by row: the roles allowed to perform each action
MATRIX: dict[Action, set[WorkspaceRole]] = {
    Action.VIEW_GRANTED_DOCS: {GUEST, MEMBER, ADMIN, OWNER},
    Action.UPLOAD_DOCUMENT: {MEMBER, ADMIN, OWNER},
    Action.CREATE_FOLDER: {MEMBER, ADMIN, OWNER},
    Action.CREATE_SHARE_LINK: {MEMBER, ADMIN, OWNER},
    Action.SEE_MEMBER_LIST: {MEMBER, ADMIN, OWNER},
    Action.INVITE_MEMBER: {ADMIN, OWNER},
    Action.GRANT_DOCUMENT_ACCESS: {ADMIN, OWNER},
    Action.CHANGE_MEMBER_ROLE: {ADMIN, OWNER},
    Action.REMOVE_MEMBER: {ADMIN, OWNER},
    Action.VIEW_ACTIVITY_LOG: {ADMIN, OWNER},
    Action.TRANSFER_OWNERSHIP: {OWNER},
    Action.DELETE_WORKSPACE: {OWNER},
}


def test_matrix_covers_every_action() -> None:
    assert set(MATRIX) == set(Action)


@pytest.mark.parametrize("action", list(Action))
@pytest.mark.parametrize("role", list(WorkspaceRole))
def test_role_can_do_exactly_what_the_matrix_allows(action: Action, role: WorkspaceRole) -> None:
    assert can(role, action) is (role in MATRIX[action])


def test_roles_form_a_strict_hierarchy() -> None:
    assert ROLE_LEVEL[OWNER] > ROLE_LEVEL[ADMIN] > ROLE_LEVEL[MEMBER] > ROLE_LEVEL[GUEST]


@pytest.mark.parametrize("actor", list(WorkspaceRole))
@pytest.mark.parametrize("action", [Action.CHANGE_MEMBER_ROLE, Action.REMOVE_MEMBER])
def test_nobody_can_act_on_the_owner(actor: WorkspaceRole, action: Action) -> None:
    assert can_act_on_member(actor, OWNER, action) is False


@pytest.mark.parametrize("target", [ADMIN, MEMBER, GUEST])
def test_admin_can_act_on_everyone_below_the_owner(target: WorkspaceRole) -> None:
    assert can_act_on_member(ADMIN, target, Action.REMOVE_MEMBER) is True
    assert can_act_on_member(MEMBER, target, Action.REMOVE_MEMBER) is False


FRONTEND_FILE = ROOT_DIR / "frontend" / "src" / "permissions" / "roleHierarchy.ts"


@pytest.mark.skipif(not FRONTEND_FILE.exists(), reason="frontend sources not present")
def test_backend_numbers_equal_the_frontend_copy() -> None:
    """The frontend hides controls using its own copy of these numbers; a drift would make the UI
    offer actions the API refuses (or hide ones it allows)."""
    source = FRONTEND_FILE.read_text(encoding="utf-8")

    roles_block = re.search(r"const ROLE_LEVEL[^{]*\{([^}]*)\}", source)
    assert roles_block, "could not find ROLE_LEVEL in the frontend"
    frontend_roles = {
        name: int(level) for name, level in re.findall(r"(\w+):\s*(\d+)", roles_block.group(1))
    }
    assert frontend_roles == {role.value: level for role, level in ROLE_LEVEL.items()}

    actions_block = re.search(r"export const ACTION_LEVEL\s*=\s*\{(.*?)\}\s*as const", source, re.S)
    assert actions_block, "could not find ACTION_LEVEL in the frontend"
    frontend_actions = {
        name: int(level)
        for name, level in re.findall(r"([A-Z_]+):\s*(\d+)", actions_block.group(1))
    }
    assert frontend_actions == {action.value: level for action, level in ACTION_LEVEL.items()}
