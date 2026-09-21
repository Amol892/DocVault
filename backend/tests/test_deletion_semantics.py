"""Deleting a folder never loses or hides what was inside it (FR-23)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fake_storage import FakeStorage
from tests.helpers import API, make_folder, upload_document, workspace_with_roles


async def folder_names(
    client: AsyncClient, headers: dict[str, str], workspace_id: str
) -> dict[str, str | None]:
    listed = await client.get(f"{API}/workspaces/{workspace_id}/folders", headers=headers)
    by_id = {f["id"]: f for f in listed.json()}
    return {
        f["name"]: (by_id[f["parent_folder_id"]]["name"] if f["parent_folder_id"] else None)
        for f in by_id.values()
    }


async def test_children_and_documents_move_up_one_level(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    top = await make_folder(client, member, ws, "Top")
    middle = await make_folder(client, member, ws, "Middle", top["id"])
    leaf = await make_folder(client, member, ws, "Leaf", middle["id"])
    document = await upload_document(
        client, storage, member, workspace_id=ws, folder_id=middle["id"]
    )

    assert (
        await client.delete(f"{API}/folders/{middle['id']}", headers=member.headers)
    ).status_code == 204

    assert await folder_names(client, member.headers, ws) == {"Top": None, "Leaf": "Top"}
    listed = await client.get(
        f"{API}/documents",
        params={"workspace_id": ws, "folder_id": top["id"]},
        headers=member.headers,
    )
    assert [d["id"] for d in listed.json()["items"]] == [document["id"]]
    assert leaf["id"]


async def test_deleting_a_root_folder_moves_things_to_the_root(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    top = await make_folder(client, member, ws, "Top")
    await make_folder(client, member, ws, "Sub", top["id"])
    document = await upload_document(client, storage, member, workspace_id=ws, folder_id=top["id"])

    await client.delete(f"{API}/folders/{top['id']}", headers=member.headers)

    assert await folder_names(client, member.headers, ws) == {"Sub": None}
    fetched = await client.get(
        f"{API}/documents", params={"workspace_id": ws}, headers=member.headers
    )
    assert fetched.json()["items"][0]["id"] == document["id"]
    assert fetched.json()["items"][0]["folder_id"] is None


async def test_a_name_clash_after_moving_up_is_resolved_not_lost(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    await make_folder(client, member, ws, "Reports")  # already at the root
    holder = await make_folder(client, member, ws, "Holder")
    await make_folder(client, member, ws, "Reports", holder["id"])  # will move to the root too

    assert (
        await client.delete(f"{API}/folders/{holder['id']}", headers=member.headers)
    ).status_code == 204

    names = await folder_names(client, member.headers, ws)
    assert sorted(names) == ["Reports", "Reports (moved 2)"]
    assert set(names.values()) == {None}


async def test_deleting_a_granted_folder_removes_the_grant(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    folder = await make_folder(client, member, ws, "Shared")
    document = await upload_document(
        client, storage, member, workspace_id=ws, folder_id=folder["id"]
    )
    await client.post(
        f"{API}/folders/{folder['id']}/grants",
        json={"user_id": users["guest"].id},
        headers=users["admin"].headers,
    )
    await client.delete(f"{API}/folders/{folder['id']}", headers=member.headers)

    guest = users["guest"].headers
    assert (await client.get(f"{API}/workspaces/{ws}/folders", headers=guest)).json() == []
    # the document moved to the root, where a guest sees nothing
    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 404
    still_there = await client.get(
        f"{API}/documents", params={"workspace_id": ws}, headers=member.headers
    )
    assert still_there.json()["total"] == 1
