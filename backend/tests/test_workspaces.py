"""Workspace create / list / get / delete."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from app.models.enums import WorkspaceRole
from app.models.workspace import Workspace, WorkspaceMember
from tests.helpers import API, add_member, make_user, make_workspace, workspace_with_roles


async def actions(db: AsyncSession, workspace_id: str) -> list[str]:
    result = await db.execute(
        select(ActivityLog.action)
        .where(ActivityLog.workspace_id == workspace_id)
        .order_by(ActivityLog.created_at, ActivityLog.id)
    )
    return list(result.scalars())


class TestCreate:
    async def test_creator_becomes_the_owner(self, client: AsyncClient, db: AsyncSession) -> None:
        ana = await make_user(client, "ana@example.com")
        response = await client.post(
            f"{API}/workspaces", json={"name": "Acme"}, headers=ana.headers
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Acme"
        assert body["owner_id"] == ana.id
        assert body["my_role"] == "owner"
        assert set(body) == {"id", "name", "owner_id", "created_at", "my_role"}

        members = (await db.execute(select(WorkspaceMember))).scalars().all()
        assert len(members) == 1
        assert (members[0].user_id, members[0].role) == (ana.id, WorkspaceRole.OWNER)

    async def test_creation_is_recorded_in_the_activity_log(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        ana = await make_user(client, "ana@example.com")
        workspace = await make_workspace(client, ana)
        assert await actions(db, workspace["id"]) == ["workspace.created"]

    async def test_name_is_trimmed(self, client: AsyncClient) -> None:
        ana = await make_user(client, "ana@example.com")
        body = await make_workspace(client, ana, "  Acme Corp  ")
        assert body["name"] == "Acme Corp"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 201])
    async def test_invalid_names_are_rejected(self, client: AsyncClient, name: str) -> None:
        ana = await make_user(client, "ana@example.com")
        response = await client.post(f"{API}/workspaces", json={"name": name}, headers=ana.headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_requires_a_signed_in_user(self, client: AsyncClient) -> None:
        response = await client.post(f"{API}/workspaces", json={"name": "Acme"})
        assert response.status_code == 401

    async def test_one_user_can_own_several_workspaces_with_the_same_name(
        self, client: AsyncClient
    ) -> None:
        ana = await make_user(client, "ana@example.com")
        first = await make_workspace(client, ana, "Same")
        second = await make_workspace(client, ana, "Same")
        assert first["id"] != second["id"]


class TestList:
    async def test_lists_only_workspaces_the_caller_belongs_to(self, client: AsyncClient) -> None:
        ana = await make_user(client, "ana@example.com")
        bob = await make_user(client, "bob@example.com")
        mine = await make_workspace(client, ana, "Ana's")
        await make_workspace(client, bob, "Bob's")

        response = await client.get(f"{API}/workspaces", headers=ana.headers)
        assert response.status_code == 200
        assert response.json() == [{"id": mine["id"], "name": "Ana's", "role": "owner"}]

    async def test_includes_workspaces_joined_as_any_role_sorted_by_name(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        ana = await make_user(client, "ana@example.com")
        bob = await make_user(client, "bob@example.com")
        zed = await make_workspace(client, bob, "Zed")
        alpha = await make_workspace(client, bob, "Alpha")
        await add_member(db, zed["id"], ana, WorkspaceRole.GUEST)
        await add_member(db, alpha["id"], ana, WorkspaceRole.MEMBER)

        body = (await client.get(f"{API}/workspaces", headers=ana.headers)).json()
        assert [(w["name"], w["role"]) for w in body] == [("Alpha", "member"), ("Zed", "guest")]

    async def test_a_new_user_sees_an_empty_list(self, client: AsyncClient) -> None:
        ana = await make_user(client, "ana@example.com")
        response = await client.get(f"{API}/workspaces", headers=ana.headers)
        assert response.status_code == 200
        assert response.json() == []


class TestGet:
    async def test_every_role_can_open_the_workspace_and_sees_their_own_role(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        for role in ("owner", "admin", "member", "guest"):
            response = await client.get(
                f"{API}/workspaces/{workspace['id']}", headers=users[role].headers
            )
            assert response.status_code == 200, role
            assert response.json()["my_role"] == role
            assert response.json()["owner_id"] == users["owner"].id

    async def test_a_guest_can_open_a_workspace_without_the_member_list(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """The frontend reads my_role from here because guests cannot list members."""
        workspace, users = await workspace_with_roles(client, db)
        opened = await client.get(
            f"{API}/workspaces/{workspace['id']}", headers=users["guest"].headers
        )
        members = await client.get(
            f"{API}/workspaces/{workspace['id']}/members", headers=users["guest"].headers
        )
        assert opened.status_code == 200
        assert members.status_code == 403


class TestDelete:
    async def test_the_owner_soft_deletes_it_and_it_disappears_for_everyone(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)

        response = await client.delete(
            f"{API}/workspaces/{workspace['id']}", headers=users["owner"].headers
        )
        assert response.status_code == 204

        # soft delete: the row is kept, marked deleted
        row = (
            await db.execute(select(Workspace).where(Workspace.id == workspace["id"]))
        ).scalar_one()
        assert row.deleted_at is not None

        for role in ("owner", "admin", "member", "guest"):
            gone = await client.get(
                f"{API}/workspaces/{workspace['id']}", headers=users[role].headers
            )
            assert gone.status_code == 404, role
            listing = await client.get(f"{API}/workspaces", headers=users[role].headers)
            assert listing.json() == [], role
        members = await client.get(
            f"{API}/workspaces/{workspace['id']}/members", headers=users["owner"].headers
        )
        assert members.status_code == 404

    async def test_deletion_is_recorded(self, client: AsyncClient, db: AsyncSession) -> None:
        workspace, users = await workspace_with_roles(client, db)
        await client.delete(f"{API}/workspaces/{workspace['id']}", headers=users["owner"].headers)
        assert await actions(db, workspace["id"]) == ["workspace.created", "workspace.deleted"]

    @pytest.mark.parametrize("role", ["admin", "member", "guest"])
    async def test_only_the_owner_may_delete(
        self, client: AsyncClient, db: AsyncSession, role: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.delete(
            f"{API}/workspaces/{workspace['id']}", headers=users[role].headers
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        still_there = await client.get(
            f"{API}/workspaces/{workspace['id']}", headers=users["owner"].headers
        )
        assert still_there.status_code == 200
