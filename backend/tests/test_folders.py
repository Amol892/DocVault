"""Folder create / list / rename / delete (FR-21..23)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import API, make_folder, make_user, make_workspace, workspace_with_roles


async def test_member_creates_and_lists_folders(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    created = await make_folder(client, users["member"], workspace["id"], "Contracts")
    assert created["name"] == "Contracts"
    assert created["workspace_id"] == workspace["id"]
    assert created["parent_folder_id"] is None

    listed = await client.get(
        f"{API}/workspaces/{workspace['id']}/folders", headers=users["admin"].headers
    )
    assert listed.status_code == 200
    assert [f["name"] for f in listed.json()] == ["Contracts"]


async def test_guest_cannot_create_a_folder(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    response = await client.post(
        f"{API}/workspaces/{workspace['id']}/folders",
        json={"name": "Nope"},
        headers=users["guest"].headers,
    )
    assert response.status_code == 403


async def test_outsider_gets_404_for_list_and_create(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    url = f"{API}/workspaces/{workspace['id']}/folders"
    assert (await client.get(url, headers=users["outsider"].headers)).status_code == 404
    created = await client.post(url, json={"name": "X"}, headers=users["outsider"].headers)
    assert created.status_code == 404


async def test_requires_authentication(client: AsyncClient, db: AsyncSession) -> None:
    workspace, _ = await workspace_with_roles(client, db)
    assert (await client.get(f"{API}/workspaces/{workspace['id']}/folders")).status_code == 401


async def test_nested_folder(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    parent = await make_folder(client, users["member"], workspace["id"], "Legal")
    child = await make_folder(client, users["member"], workspace["id"], "2026", parent["id"])
    assert child["parent_folder_id"] == parent["id"]


async def test_sibling_names_are_unique_ignoring_case(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    await make_folder(client, users["member"], workspace["id"], "Contracts")
    clash = await client.post(
        f"{API}/workspaces/{workspace['id']}/folders",
        json={"name": "contracts"},
        headers=users["member"].headers,
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "NAME_TAKEN"


async def test_same_name_is_fine_under_different_parents(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    a = await make_folder(client, users["member"], workspace["id"], "A")
    b = await make_folder(client, users["member"], workspace["id"], "B")
    await make_folder(client, users["member"], workspace["id"], "Archive", a["id"])
    await make_folder(client, users["member"], workspace["id"], "Archive", b["id"])


async def test_parent_from_another_workspace_is_404(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    other = await make_workspace(client, users["outsider"], "Other")
    foreign = await make_folder(client, users["outsider"], other["id"], "Secret")
    response = await client.post(
        f"{API}/workspaces/{workspace['id']}/folders",
        json={"name": "Sneaky", "parent_folder_id": foreign["id"]},
        headers=users["owner"].headers,
    )
    assert response.status_code == 404


async def test_nesting_depth_is_capped(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    parent: str | None = None
    for level in range(20):
        folder = await make_folder(client, users["owner"], workspace["id"], f"L{level}", parent)
        parent = folder["id"]
    response = await client.post(
        f"{API}/workspaces/{workspace['id']}/folders",
        json={"name": "too deep", "parent_folder_id": parent},
        headers=users["owner"].headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FOLDER_TOO_DEEP"


@pytest.mark.parametrize("name", ["", "   ", "a/b", "a\\b", "bad\nname", "x" * 256])
async def test_invalid_folder_names_are_rejected(
    client: AsyncClient, db: AsyncSession, name: str
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    response = await client.post(
        f"{API}/workspaces/{workspace['id']}/folders",
        json={"name": name},
        headers=users["owner"].headers,
    )
    assert response.status_code == 422


async def test_rename(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "Old")
    await make_folder(client, users["member"], workspace["id"], "Taken")

    renamed = await client.patch(
        f"{API}/folders/{folder['id']}", json={"name": "New"}, headers=users["member"].headers
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "New"

    clash = await client.patch(
        f"{API}/folders/{folder['id']}", json={"name": "taken"}, headers=users["member"].headers
    )
    assert clash.status_code == 409


async def test_guest_cannot_rename_or_delete(client: AsyncClient, db: AsyncSession) -> None:
    """Guests have no standing on any folder (FR-21: access is per document, not per folder), so
    this is a 404 like any folder they were never near, not a 403."""
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "Docs")
    guest = users["guest"].headers
    renamed = await client.patch(f"{API}/folders/{folder['id']}", json={"name": "x"}, headers=guest)
    assert renamed.status_code == 404
    assert (await client.delete(f"{API}/folders/{folder['id']}", headers=guest)).status_code == 404


async def test_delete_hides_the_folder(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "Temp")
    deleted = await client.delete(f"{API}/folders/{folder['id']}", headers=users["member"].headers)
    assert deleted.status_code == 204
    listed = await client.get(
        f"{API}/workspaces/{workspace['id']}/folders", headers=users["member"].headers
    )
    assert listed.json() == []
    again = await client.delete(f"{API}/folders/{folder['id']}", headers=users["member"].headers)
    assert again.status_code == 404
    # the name is free again
    await make_folder(client, users["member"], workspace["id"], "Temp")


async def test_unknown_folder_is_404(client: AsyncClient) -> None:
    user = await make_user(client, "solo@example.com")
    response = await client.patch(f"{API}/folders/nope", json={"name": "x"}, headers=user.headers)
    assert response.status_code == 404
