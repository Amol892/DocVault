"""The workspace activity feed (FR-29, FR-30): Admin+ only, scoped to one workspace."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fake_storage import FakeStorage
from tests.helpers import API, make_workspace, upload_document, workspace_with_roles


async def feed(client: AsyncClient, headers: dict[str, str], workspace_id: str, page: int = 1):
    return await client.get(
        f"{API}/workspaces/{workspace_id}/activity", params={"page": page}, headers=headers
    )


async def test_admin_and_owner_see_the_feed_newest_first(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    await client.post(
        f"{API}/documents/{document['id']}/grants",
        json={"user_id": users["guest"].id},
        headers=users["admin"].headers,
    )
    for role in ("owner", "admin"):
        response = await feed(client, users[role].headers, workspace["id"])
        assert response.status_code == 200, role
        body = response.json()
        assert body["page"] == 1 and body["total"] == 2
        assert [e["action"] for e in body["items"]] == [
            "guest.document_granted",
            "workspace.created",
        ]
        first = body["items"][0]
        assert first["actor_name"] == users["admin"].name
        assert first["target_id"] == users["guest"].id
        assert first["metadata"] == {"document_id": document["id"]}


async def test_members_and_guests_cannot_see_it(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    for role in ("member", "guest"):
        assert (await feed(client, users[role].headers, workspace["id"])).status_code == 403


async def test_outsiders_get_404_and_anonymous_gets_401(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    assert (await feed(client, users["outsider"].headers, workspace["id"])).status_code == 404
    assert (await client.get(f"{API}/workspaces/{workspace['id']}/activity")).status_code == 401


async def test_the_feed_never_shows_another_workspaces_events(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    other = await make_workspace(client, users["outsider"], "Other")
    mine = (await feed(client, users["owner"].headers, workspace["id"])).json()
    theirs = (await feed(client, users["outsider"].headers, other["id"])).json()
    assert mine["total"] == 1 and theirs["total"] == 1
    assert mine["items"][0]["id"] != theirs["items"][0]["id"]


async def test_pagination(client: AsyncClient, db: AsyncSession, storage: FakeStorage) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    for _ in range(2):  # grant then revoke, 4 entries with the creation event: 5 in all
        await client.post(
            f"{API}/documents/{document['id']}/grants",
            json={"user_id": users["guest"].id},
            headers=users["admin"].headers,
        )
        await client.delete(
            f"{API}/documents/{document['id']}/grants/{users['guest'].id}",
            headers=users["admin"].headers,
        )
    body = (await feed(client, users["owner"].headers, workspace["id"])).json()
    assert body["total"] == 5 and len(body["items"]) == 5
    empty = (await feed(client, users["owner"].headers, workspace["id"], page=2)).json()
    assert empty["items"] == [] and empty["total"] == 5
    assert (await feed(client, users["owner"].headers, workspace["id"], page=0)).status_code == 422
