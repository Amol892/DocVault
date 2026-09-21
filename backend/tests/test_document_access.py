"""Risk area: who can reach which document and folder. Every "no" that must not reveal existence
has to be byte-for-byte the same 404 as a document or folder that does not exist."""

from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fake_storage import FakeStorage
from tests.helpers import (
    API,
    TestUser,
    make_folder,
    make_user,
    make_workspace,
    upload_document,
    workspace_with_roles,
)


async def call(
    client: AsyncClient, user: TestUser, method: str, path: str, body: dict[str, Any] | None = None
) -> Response:
    return await client.request(method, f"{API}{path}", json=body, headers=user.headers)


def document_requests(
    document_id: str, folder_id: str
) -> list[tuple[str, str, dict[str, Any] | None]]:
    return [
        ("GET", f"/documents/{document_id}/download-url", None),
        ("POST", f"/documents/{document_id}/confirm-upload", None),
        ("PATCH", f"/documents/{document_id}", {"filename": "x.pdf"}),
        ("PATCH", f"/documents/{document_id}", {"folder_id": None}),
        ("DELETE", f"/documents/{document_id}", None),
        ("PATCH", f"/folders/{folder_id}", {"name": "renamed"}),
        ("DELETE", f"/folders/{folder_id}", None),
        ("POST", f"/folders/{folder_id}/grants", {"user_id": "someone"}),
        ("DELETE", f"/folders/{folder_id}/grants/someone", None),
    ]


async def test_hidden_things_look_exactly_like_missing_ones(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "Secret")
    document = await upload_document(
        client, storage, users["member"], workspace_id=workspace["id"], folder_id=folder["id"]
    )
    personal = await upload_document(client, storage, users["member"], filename="mine.pdf")
    stranger_owner = await make_user(client, "stranger@example.com")
    await make_workspace(client, stranger_owner, "Elsewhere")

    # (who, what they try to reach)
    attempts: list[tuple[TestUser, str, str]] = [
        (users["outsider"], document["id"], folder["id"]),  # in no workspace
        (stranger_owner, document["id"], folder["id"]),  # Owner of a different workspace
        (users["guest"], document["id"], folder["id"]),  # a guest with no grant
        (users["owner"], personal["id"], folder["id"]),  # someone else's personal document
        (users["admin"], personal["id"], folder["id"]),
    ]
    for actor, document_id, folder_id in attempts:
        for method, path, body in document_requests(document_id, folder_id):
            real = await call(client, actor, method, path, body)
            missing_path = path.replace(document_id, "doesnotexist1").replace(
                folder_id, "doesnotexist2"
            )
            # the personal document is reachable by requests that only touch the folder
            if document_id == personal["id"] and "/folders/" in path:
                continue
            missing = await call(client, actor, method, missing_path, body)
            assert real.status_code == 404, (actor.email, method, path, real.status_code)
            assert real.json() == missing.json(), (actor.email, method, path)


async def test_upload_of_a_new_version_to_a_hidden_document_is_404(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    personal = await upload_document(client, storage, users["member"], filename="mine.pdf")
    body = {"filename": "v2.pdf", "mime_type": "application/pdf", "size_bytes": 10}
    for actor, target in [(users["outsider"], document["id"]), (users["owner"], personal["id"])]:
        response = await client.post(
            f"{API}/documents/upload-url",
            json={**body, "document_id": target},
            headers=actor.headers,
        )
        assert response.status_code == 404


async def test_guest_with_a_grant_can_read_but_never_write(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "Shared")
    document = await upload_document(
        client, storage, users["member"], workspace_id=workspace["id"], folder_id=folder["id"]
    )
    await client.post(
        f"{API}/folders/{folder['id']}/grants",
        json={"user_id": users["guest"].id},
        headers=users["admin"].headers,
    )
    guest = users["guest"]

    assert (
        await call(client, guest, "GET", f"/documents/{document['id']}/download-url")
    ).status_code == 200
    listed = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=guest.headers
    )
    assert [d["id"] for d in listed.json()["items"]] == [document["id"]]

    forbidden = [
        ("PATCH", f"/documents/{document['id']}", {"filename": "x.pdf"}),
        ("DELETE", f"/documents/{document['id']}", None),
        ("POST", f"/documents/{document['id']}/confirm-upload", None),
        ("PATCH", f"/folders/{folder['id']}", {"name": "x"}),
        ("POST", f"/folders/{folder['id']}/grants", {"user_id": guest.id}),
    ]
    for method, path, body in forbidden:
        assert (await call(client, guest, method, path, body)).status_code == 403, (method, path)
    version = await client.post(
        f"{API}/documents/upload-url",
        json={
            "filename": "v.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "document_id": document["id"],
        },
        headers=guest.headers,
    )
    assert version.status_code == 403
    new_in_folder = await client.post(
        f"{API}/documents/upload-url",
        json={
            "filename": "n.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "workspace_id": workspace["id"],
            "folder_id": folder["id"],
        },
        headers=guest.headers,
    )
    assert new_in_folder.status_code == 403


async def test_guest_sees_only_documents_in_granted_folders(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    granted = await make_folder(client, member, ws, "Granted")
    child = await make_folder(client, member, ws, "Child", granted["id"])
    other = await make_folder(client, member, ws, "Other")
    seen = [
        await upload_document(client, storage, member, workspace_id=ws, folder_id=granted["id"]),
        await upload_document(client, storage, member, workspace_id=ws, folder_id=child["id"]),
    ]
    hidden = [
        await upload_document(client, storage, member, workspace_id=ws, folder_id=other["id"]),
        await upload_document(client, storage, member, workspace_id=ws),  # workspace root
    ]
    await client.post(
        f"{API}/folders/{granted['id']}/grants",
        json={"user_id": users["guest"].id},
        headers=users["admin"].headers,
    )
    guest = users["guest"]

    listed = await client.get(
        f"{API}/documents", params={"workspace_id": ws}, headers=guest.headers
    )
    assert sorted(d["id"] for d in listed.json()["items"]) == sorted(d["id"] for d in seen)
    assert listed.json()["total"] == 2
    for document in hidden:
        response = await call(client, guest, "GET", f"/documents/{document['id']}/download-url")
        assert response.status_code == 404
    other_folder = await client.get(
        f"{API}/documents",
        params={"workspace_id": ws, "folder_id": other["id"]},
        headers=guest.headers,
    )
    assert other_folder.status_code == 404
    searched = await client.get(
        f"{API}/documents", params={"workspace_id": ws, "q": "report"}, headers=guest.headers
    )
    assert searched.json()["total"] == 2  # search cannot widen what a guest may see


async def test_member_cannot_move_a_document_into_a_hidden_place(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    response = await call(
        client, users["member"], "PATCH", f"/documents/{document['id']}", {"folder_id": "nope"}
    )
    assert response.status_code == 404


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
async def test_members_and_above_can_work_on_workspace_documents(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage, role: str
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    actor = users[role]
    assert (
        await call(client, actor, "GET", f"/documents/{document['id']}/download-url")
    ).status_code == 200
    renamed = await call(
        client, actor, "PATCH", f"/documents/{document['id']}", {"filename": "r.pdf"}
    )
    assert renamed.status_code == 200
    assert (await call(client, actor, "DELETE", f"/documents/{document['id']}")).status_code == 204


async def test_removed_member_loses_access_at_once(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["owner"], workspace_id=workspace["id"])
    member = users["member"]
    assert (
        await call(client, member, "GET", f"/documents/{document['id']}/download-url")
    ).status_code == 200
    removed = await call(
        client, users["owner"], "DELETE", f"/workspaces/{workspace['id']}/members/{member.id}"
    )
    assert removed.status_code == 204
    assert (
        await call(client, member, "GET", f"/documents/{document['id']}/download-url")
    ).status_code == 404


async def test_deleted_workspace_hides_its_documents(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    assert (
        await call(client, users["owner"], "DELETE", f"/workspaces/{workspace['id']}")
    ).status_code == 204
    assert (
        await call(client, users["member"], "GET", f"/documents/{document['id']}/download-url")
    ).status_code == 404
    listed = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=users["owner"].headers
    )
    assert listed.status_code == 404


async def test_endpoints_need_a_token(client: AsyncClient) -> None:
    for method, path in [
        ("GET", "/documents"),
        ("POST", "/documents/upload-url"),
        ("POST", "/documents/x/confirm-upload"),
        ("GET", "/documents/x/download-url"),
        ("PATCH", "/documents/x"),
        ("DELETE", "/documents/x"),
        ("PATCH", "/folders/x"),
        ("DELETE", "/folders/x"),
        ("POST", "/folders/x/grants"),
        ("DELETE", "/folders/x/grants/y"),
    ]:
        assert (await client.request(method, f"{API}{path}")).status_code == 401, (method, path)
