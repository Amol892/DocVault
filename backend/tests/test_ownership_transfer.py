"""Ownership transfer (FR-20): always exactly one Owner; only to an Admin, only by the Owner."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from app.models.enums import WorkspaceRole
from app.models.workspace import Workspace, WorkspaceMember
from tests.helpers import API, TestUser, add_member, make_user, make_workspace, workspace_with_roles


def transfer_url(workspace_id: str, user: TestUser) -> str:
    return f"{API}/workspaces/{workspace_id}/members/{user.id}/transfer-ownership"


async def owner_count(db: AsyncSession, workspace_id: str) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WorkspaceRole.OWNER,
        )
    )
    return result.scalar_one()


async def declared_owner(db: AsyncSession, workspace_id: str) -> str:
    result = await db.execute(select(Workspace.owner_id).where(Workspace.id == workspace_id))
    return result.scalar_one()


class TestTransfer:
    async def test_the_owner_hands_over_to_an_admin(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        old_owner, new_owner = users["owner"], users["admin"]

        response = await client.post(
            transfer_url(workspace["id"], new_owner), headers=old_owner.headers
        )
        assert response.status_code == 204

        # roles swapped, and the workspace record agrees
        assert await owner_count(db, workspace["id"]) == 1
        assert await declared_owner(db, workspace["id"]) == new_owner.id
        now_new = await client.get(f"{API}/workspaces/{workspace['id']}", headers=new_owner.headers)
        now_old = await client.get(f"{API}/workspaces/{workspace['id']}", headers=old_owner.headers)
        assert now_new.json()["my_role"] == "owner"
        assert now_old.json()["my_role"] == "admin"
        assert now_new.json()["owner_id"] == new_owner.id

    async def test_it_is_recorded_in_the_activity_log(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        await client.post(
            transfer_url(workspace["id"], users["admin"]), headers=users["owner"].headers
        )
        result = await db.execute(
            select(ActivityLog).where(ActivityLog.action == "ownership.transferred")
        )
        (entry,) = result.scalars().all()
        assert entry.actor_id == users["owner"].id
        assert entry.metadata_ == {"from": users["owner"].id, "to": users["admin"].id}

    async def test_the_former_owner_loses_owner_only_powers(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        old_owner, new_owner = users["owner"], users["admin"]
        await client.post(transfer_url(workspace["id"], new_owner), headers=old_owner.headers)

        again = await client.post(
            transfer_url(workspace["id"], new_owner), headers=old_owner.headers
        )
        delete = await client.delete(
            f"{API}/workspaces/{workspace['id']}", headers=old_owner.headers
        )
        assert again.status_code == 403
        assert delete.status_code == 403

    async def test_the_new_owner_gets_them(self, client: AsyncClient, db: AsyncSession) -> None:
        workspace, users = await workspace_with_roles(client, db)
        await client.post(
            transfer_url(workspace["id"], users["admin"]), headers=users["owner"].headers
        )
        delete = await client.delete(
            f"{API}/workspaces/{workspace['id']}", headers=users["admin"].headers
        )
        assert delete.status_code == 204

    async def test_ownership_can_be_handed_back(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        await client.post(
            transfer_url(workspace["id"], users["admin"]), headers=users["owner"].headers
        )
        back = await client.post(
            transfer_url(workspace["id"], users["owner"]), headers=users["admin"].headers
        )
        assert back.status_code == 204
        assert await declared_owner(db, workspace["id"]) == users["owner"].id
        assert await owner_count(db, workspace["id"]) == 1


class TestRefusals:
    @pytest.mark.parametrize("target", ["member", "guest"])
    async def test_only_an_existing_admin_can_receive_ownership(
        self, client: AsyncClient, db: AsyncSession, target: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.post(
            transfer_url(workspace["id"], users[target]), headers=users["owner"].headers
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "TARGET_MUST_BE_ADMIN"
        assert await declared_owner(db, workspace["id"]) == users["owner"].id
        assert await owner_count(db, workspace["id"]) == 1

    async def test_the_owner_cannot_transfer_to_themself(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.post(
            transfer_url(workspace["id"], users["owner"]), headers=users["owner"].headers
        )
        assert response.status_code == 409
        assert await owner_count(db, workspace["id"]) == 1

    async def test_a_non_member_target_is_404(self, client: AsyncClient, db: AsyncSession) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.post(
            transfer_url(workspace["id"], users["outsider"]), headers=users["owner"].headers
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("actor", ["admin", "member", "guest"])
    async def test_only_the_owner_can_transfer(
        self, client: AsyncClient, db: AsyncSession, actor: str
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.post(
            transfer_url(workspace["id"], users["admin"]), headers=users[actor].headers
        )
        assert response.status_code == 403
        assert await declared_owner(db, workspace["id"]) == users["owner"].id


class TestConcurrency:
    async def test_two_simultaneous_transfers_cannot_both_win(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """The workspace row is locked, so the second transfer sees it is no longer the Owner."""
        workspace, users = await workspace_with_roles(client, db)
        second_admin = await make_user(client, "admin2@example.com")
        await add_member(db, workspace["id"], second_admin, WorkspaceRole.ADMIN)

        first, second = await asyncio.gather(
            client.post(
                transfer_url(workspace["id"], users["admin"]), headers=users["owner"].headers
            ),
            client.post(
                transfer_url(workspace["id"], second_admin), headers=users["owner"].headers
            ),
        )

        assert sorted([first.status_code, second.status_code]) == [204, 403]
        assert await owner_count(db, workspace["id"]) == 1
        winner = users["admin"] if first.status_code == 204 else second_admin
        assert await declared_owner(db, workspace["id"]) == winner.id

    async def test_a_new_workspace_always_has_exactly_one_owner(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        ana = await make_user(client, "ana@example.com")
        workspace = await make_workspace(client, ana)
        assert await owner_count(db, workspace["id"]) == 1
        assert await declared_owner(db, workspace["id"]) == ana.id
