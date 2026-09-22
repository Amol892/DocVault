"""Members: listing, changing roles and removing people (FR-19, PRD 05/06)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from app.models.document import Document, DocumentGrant
from app.models.enums import WorkspaceRole
from app.models.workspace import WorkspaceMember
from tests.helpers import API, TestUser, workspace_with_roles


async def role_of(db: AsyncSession, workspace_id: str, user_id: str) -> WorkspaceRole | None:
    result = await db.execute(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def log_entries(db: AsyncSession, workspace_id: str, action: str) -> list[ActivityLog]:
    result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.workspace_id == workspace_id, ActivityLog.action == action
        )
    )
    return list(result.scalars())


async def grant_document(
    db: AsyncSession, workspace_id: str, owner: TestUser, guest: TestUser, filename: str = "R.pdf"
) -> str:
    document = Document(workspace_id=workspace_id, owner_id=owner.id, filename=filename)
    db.add(document)
    await db.flush()
    db.add(
        DocumentGrant(
            workspace_id=workspace_id,
            document_id=document.id,
            user_id=guest.id,
            granted_by=owner.id,
        )
    )
    await db.commit()
    return document.id


def member_url(workspace_id: str, user: TestUser) -> str:
    return f"{API}/workspaces/{workspace_id}/members/{user.id}"


class TestListMembers:
    @pytest.mark.parametrize("role", ["owner", "admin", "member"])
    async def test_member_and_above_can_see_the_list(
        self, client: AsyncClient, db: AsyncSession, role: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.get(
            f"{API}/workspaces/{workspace['id']}/members", headers=users[role].headers
        )
        assert response.status_code == 200
        listed = {m["user_id"]: m["role"] for m in response.json()}
        assert listed == {
            users["owner"].id: "owner",
            users["admin"].id: "admin",
            users["member"].id: "member",
            users["guest"].id: "guest",
        }
        assert users["outsider"].id not in listed

    async def test_each_entry_has_the_documented_fields(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        body = (
            await client.get(
                f"{API}/workspaces/{workspace['id']}/members", headers=users["owner"].headers
            )
        ).json()
        assert set(body[0]) == {
            "user_id",
            "name",
            "email",
            "role",
            "joined_at",
            "granted_document_ids",
        }
        assert [m["role"] for m in body][0] == "owner"  # listed in the order they joined

    async def test_a_guest_cannot_see_the_list(self, client: AsyncClient, db: AsyncSession) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.get(
            f"{API}/workspaces/{workspace['id']}/members", headers=users["guest"].headers
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    async def test_guests_carry_their_granted_documents_and_others_do_not(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        document_id = await grant_document(db, workspace["id"], users["owner"], users["guest"])

        body = (
            await client.get(
                f"{API}/workspaces/{workspace['id']}/members", headers=users["admin"].headers
            )
        ).json()
        by_role = {m["role"]: m["granted_document_ids"] for m in body}
        assert by_role["guest"] == [document_id]
        assert by_role["owner"] is by_role["admin"] is by_role["member"] is None


class TestRemoval:
    async def test_access_ends_on_the_very_next_request(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        member = users["member"]
        before = await client.get(f"{API}/workspaces/{workspace['id']}", headers=member.headers)
        assert before.status_code == 200

        removed = await client.delete(
            member_url(workspace["id"], member), headers=users["admin"].headers
        )
        assert removed.status_code == 204

        # same token, no re-login: the membership row is the whole authorization
        after = await client.get(f"{API}/workspaces/{workspace['id']}", headers=member.headers)
        assert after.status_code == 404
        assert (await client.get(f"{API}/workspaces", headers=member.headers)).json() == []
        assert (await client.get(f"{API}/auth/me", headers=member.headers)).status_code == 200
        assert await role_of(db, workspace["id"], member.id) is None

    async def test_removal_is_recorded(self, client: AsyncClient, db: AsyncSession) -> None:
        workspace, users = await workspace_with_roles(client, db)
        await client.delete(
            member_url(workspace["id"], users["member"]), headers=users["admin"].headers
        )
        (entry,) = await log_entries(db, workspace["id"], "member.removed")
        assert entry.actor_id == users["admin"].id
        assert entry.target_id == users["member"].id
        assert entry.metadata_ == {"role": "member"}

    async def test_a_removed_guests_document_grants_go_with_them(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        await grant_document(db, workspace["id"], users["owner"], users["guest"])
        assert (await db.execute(select(func.count()).select_from(DocumentGrant))).scalar_one() == 1

        response = await client.delete(
            member_url(workspace["id"], users["guest"]), headers=users["owner"].headers
        )
        assert response.status_code == 204
        assert (await db.execute(select(func.count()).select_from(DocumentGrant))).scalar_one() == 0

    async def test_the_owner_can_remove_an_admin(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.delete(
            member_url(workspace["id"], users["admin"]), headers=users["owner"].headers
        )
        assert response.status_code == 204

    @pytest.mark.parametrize("actor", ["owner", "admin", "member", "guest"])
    async def test_nobody_can_remove_the_owner(
        self, client: AsyncClient, db: AsyncSession, actor: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.delete(
            member_url(workspace["id"], users["owner"]), headers=users[actor].headers
        )
        assert response.status_code in (403,)
        if actor in ("owner", "admin"):
            assert response.json()["error"]["code"] == "CANNOT_MODIFY_OWNER"
        assert await role_of(db, workspace["id"], users["owner"].id) == WorkspaceRole.OWNER

    @pytest.mark.parametrize("actor", ["member", "guest"])
    async def test_members_and_guests_cannot_remove_anyone(
        self, client: AsyncClient, db: AsyncSession, actor: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.delete(
            member_url(workspace["id"], users["admin"]), headers=users[actor].headers
        )
        assert response.status_code == 403
        assert await role_of(db, workspace["id"], users["admin"].id) == WorkspaceRole.ADMIN

    async def test_removing_someone_who_is_not_a_member_is_404(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.delete(
            member_url(workspace["id"], users["outsider"]), headers=users["owner"].headers
        )
        assert response.status_code == 404

    async def test_removing_twice_the_second_time_is_404(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        url = member_url(workspace["id"], users["member"])
        assert (await client.delete(url, headers=users["admin"].headers)).status_code == 204
        assert (await client.delete(url, headers=users["admin"].headers)).status_code == 404


class TestRoleChange:
    async def test_admin_changes_a_members_role_and_it_is_recorded(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.patch(
            member_url(workspace["id"], users["member"]),
            json={"role": "admin"},
            headers=users["admin"].headers,
        )
        assert response.status_code == 204
        assert await role_of(db, workspace["id"], users["member"].id) == WorkspaceRole.ADMIN
        (entry,) = await log_entries(db, workspace["id"], "member.role_changed")
        assert entry.metadata_ == {"from": "member", "to": "admin"}
        assert entry.actor_id == users["admin"].id

    async def test_the_new_role_applies_on_the_next_request(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        member = users["member"]
        members_url = f"{API}/workspaces/{workspace['id']}/members"
        assert (await client.get(members_url, headers=member.headers)).status_code == 200

        await client.patch(
            member_url(workspace["id"], member),
            json={"role": "guest"},
            headers=users["admin"].headers,
        )
        assert (await client.get(members_url, headers=member.headers)).status_code == 403
        me = await client.get(f"{API}/workspaces/{workspace['id']}", headers=member.headers)
        assert me.json()["my_role"] == "guest"

    @pytest.mark.parametrize("role", ["owner", "superuser", "", None])
    async def test_you_cannot_set_the_owner_role_or_an_unknown_one(
        self, client: AsyncClient, db: AsyncSession, role: str | None
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.patch(
            member_url(workspace["id"], users["member"]),
            json={"role": role},
            headers=users["owner"].headers,
        )
        assert response.status_code == 422
        assert await role_of(db, workspace["id"], users["member"].id) == WorkspaceRole.MEMBER

    @pytest.mark.parametrize("actor", ["owner", "admin"])
    async def test_the_owners_role_cannot_be_changed(
        self, client: AsyncClient, db: AsyncSession, actor: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.patch(
            member_url(workspace["id"], users["owner"]),
            json={"role": "guest"},
            headers=users[actor].headers,
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CANNOT_MODIFY_OWNER"
        assert await role_of(db, workspace["id"], users["owner"].id) == WorkspaceRole.OWNER

    @pytest.mark.parametrize("actor", ["member", "guest"])
    async def test_members_and_guests_cannot_change_roles(
        self, client: AsyncClient, db: AsyncSession, actor: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.patch(
            member_url(workspace["id"], users["guest"]),
            json={"role": "admin"},
            headers=users[actor].headers,
        )
        assert response.status_code == 403
        assert await role_of(db, workspace["id"], users["guest"].id) == WorkspaceRole.GUEST

    async def test_a_member_cannot_promote_themself(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.patch(
            member_url(workspace["id"], users["member"]),
            json={"role": "admin"},
            headers=users["member"].headers,
        )
        assert response.status_code == 403
        assert await role_of(db, workspace["id"], users["member"].id) == WorkspaceRole.MEMBER

    async def test_leaving_the_guest_role_clears_document_grants(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        await grant_document(db, workspace["id"], users["owner"], users["guest"])

        response = await client.patch(
            member_url(workspace["id"], users["guest"]),
            json={"role": "member"},
            headers=users["admin"].headers,
        )
        assert response.status_code == 204
        assert (await db.execute(select(func.count()).select_from(DocumentGrant))).scalar_one() == 0

    async def test_setting_the_same_role_is_a_quiet_no_op(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.patch(
            member_url(workspace["id"], users["member"]),
            json={"role": "member"},
            headers=users["admin"].headers,
        )
        assert response.status_code == 204
        assert await log_entries(db, workspace["id"], "member.role_changed") == []

    async def test_changing_a_non_member_is_404(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.patch(
            member_url(workspace["id"], users["outsider"]),
            json={"role": "member"},
            headers=users["owner"].headers,
        )
        assert response.status_code == 404
