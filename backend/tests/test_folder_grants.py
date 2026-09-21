"""Guest folder grants (FR-22): who can grant, what a guest then sees, revocation."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from tests.fake_storage import FakeStorage
from tests.helpers import API, make_folder, upload_document, workspace_with_roles


async def grant(client: AsyncClient, actor_headers: dict[str, str], folder_id: str, user_id: str):
    return await client.post(
        f"{API}/folders/{folder_id}/grants", json={"user_id": user_id}, headers=actor_headers
    )


async def test_admin_grants_a_guest_and_the_guest_sees_exactly_that_tree(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member = users["member"]
    shared = await make_folder(client, member, workspace["id"], "Shared")
    inside = await make_folder(client, member, workspace["id"], "Inside", shared["id"])
    await make_folder(client, member, workspace["id"], "Private")

    assert (
        await grant(client, users["admin"].headers, shared["id"], users["guest"].id)
    ).status_code == 204

    listed = await client.get(
        f"{API}/workspaces/{workspace['id']}/folders", headers=users["guest"].headers
    )
    assert sorted(f["id"] for f in listed.json()) == sorted([shared["id"], inside["id"]])


async def test_guest_without_grants_sees_no_folders(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    await make_folder(client, users["member"], workspace["id"], "Private")
    listed = await client.get(
        f"{API}/workspaces/{workspace['id']}/folders", headers=users["guest"].headers
    )
    assert listed.json() == []


async def test_only_admin_and_above_can_grant(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "F")
    for role in ("member", "guest"):
        response = await grant(client, users[role].headers, folder["id"], users["guest"].id)
        assert response.status_code in (403, 404), role
        assert response.status_code != 204
    assert (
        await grant(client, users["owner"].headers, folder["id"], users["guest"].id)
    ).status_code == 204


async def test_outsider_cannot_grant(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "F")
    response = await grant(client, users["outsider"].headers, folder["id"], users["guest"].id)
    assert response.status_code == 404


async def test_only_guests_can_be_granted(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "F")
    response = await grant(client, users["admin"].headers, folder["id"], users["member"].id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_A_GUEST"


async def test_grant_to_a_non_member_is_404(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "F")
    response = await grant(client, users["admin"].headers, folder["id"], users["outsider"].id)
    assert response.status_code == 404


async def test_grant_is_idempotent_and_logged_once(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "F")
    for _ in range(2):
        assert (
            await grant(client, users["admin"].headers, folder["id"], users["guest"].id)
        ).status_code == 204
    rows = await db.execute(
        select(ActivityLog.action).where(ActivityLog.action == "guest.folder_granted")
    )
    assert len(list(rows.scalars())) == 1


async def test_revocation_is_immediate_and_idempotent(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "F")
    document = await upload_document(
        client, storage, users["member"], workspace_id=workspace["id"], folder_id=folder["id"]
    )
    await grant(client, users["admin"].headers, folder["id"], users["guest"].id)
    guest = users["guest"].headers
    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 200

    url = f"{API}/folders/{folder['id']}/grants/{users['guest'].id}"
    assert (await client.delete(url, headers=users["admin"].headers)).status_code == 204
    assert (await client.delete(url, headers=users["admin"].headers)).status_code == 204

    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 404
    listed = await client.get(f"{API}/workspaces/{workspace['id']}/folders", headers=guest)
    assert listed.json() == []
    rows = await db.execute(
        select(ActivityLog.action).where(ActivityLog.action == "guest.folder_revoked")
    )
    assert len(list(rows.scalars())) == 1
