"""Guest document grants (FR-21): who can grant, what a guest then sees, revocation, and the
folder-pinned rule (moving a granted document, or deleting its folder, revokes the grant)."""

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from tests.fake_storage import FakeStorage
from tests.helpers import API, make_folder, upload_document, workspace_with_roles


async def grant(
    client: AsyncClient, actor_headers: dict[str, str], document_id: str, user_id: str
) -> Response:
    return await client.post(
        f"{API}/documents/{document_id}/grants", json={"user_id": user_id}, headers=actor_headers
    )


async def revoke(
    client: AsyncClient, actor_headers: dict[str, str], document_id: str, user_id: str
) -> Response:
    return await client.delete(
        f"{API}/documents/{document_id}/grants/{user_id}", headers=actor_headers
    )


async def test_admin_grants_a_guest_and_the_guest_sees_exactly_that_document(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member = users["member"]
    shared = await upload_document(
        client, storage, member, workspace_id=workspace["id"], filename="a.pdf"
    )
    other = await upload_document(
        client, storage, member, workspace_id=workspace["id"], filename="b.pdf"
    )

    assert (
        await grant(client, users["admin"].headers, shared["id"], users["guest"].id)
    ).status_code == 204

    listed = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=users["guest"].headers
    )
    assert [d["id"] for d in listed.json()["items"]] == [shared["id"]]
    assert other["id"] not in [d["id"] for d in listed.json()["items"]]


async def test_guest_without_grants_sees_no_documents_and_no_folders(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    await make_folder(client, users["member"], workspace["id"], "Private")

    listed = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=users["guest"].headers
    )
    assert listed.json()["items"] == []
    folders = await client.get(
        f"{API}/workspaces/{workspace['id']}/folders", headers=users["guest"].headers
    )
    assert folders.status_code == 200 and folders.json() == []  # guests never browse folders


async def test_a_guests_folder_id_query_is_ignored_not_a_404(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "F")
    document = await upload_document(
        client, storage, users["member"], workspace_id=workspace["id"], folder_id=folder["id"]
    )
    await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    response = await client.get(
        f"{API}/documents",
        params={"workspace_id": workspace["id"], "folder_id": folder["id"]},
        headers=users["guest"].headers,
    )
    assert response.status_code == 200
    assert [d["id"] for d in response.json()["items"]] == [document["id"]]


async def test_only_admin_and_above_can_grant(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    for role in ("member", "guest"):
        response = await grant(client, users[role].headers, document["id"], users["guest"].id)
        assert response.status_code in (403, 404), role
        assert response.status_code != 204
    assert (
        await grant(client, users["owner"].headers, document["id"], users["guest"].id)
    ).status_code == 204


async def test_outsider_cannot_grant(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    response = await grant(client, users["outsider"].headers, document["id"], users["guest"].id)
    assert response.status_code == 404


async def test_only_guests_can_be_granted(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    response = await grant(client, users["admin"].headers, document["id"], users["member"].id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_A_GUEST"


async def test_grant_to_a_non_member_is_404(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    response = await grant(client, users["admin"].headers, document["id"], users["outsider"].id)
    assert response.status_code == 404


async def test_a_personal_document_can_never_be_granted(
    client: AsyncClient, storage: FakeStorage, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    personal = await upload_document(client, storage, users["owner"], filename="mine.pdf")
    response = await grant(client, users["owner"].headers, personal["id"], users["guest"].id)
    assert response.status_code == 404


async def test_grant_is_idempotent_and_logged_once(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    for _ in range(2):
        assert (
            await grant(client, users["admin"].headers, document["id"], users["guest"].id)
        ).status_code == 204
    rows = await db.execute(
        select(ActivityLog.action).where(ActivityLog.action == "guest.document_granted")
    )
    assert len(list(rows.scalars())) == 1


async def test_revocation_is_immediate_and_idempotent(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    guest = users["guest"].headers
    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 200

    assert (
        await revoke(client, users["admin"].headers, document["id"], users["guest"].id)
    ).status_code == 204
    assert (
        await revoke(client, users["admin"].headers, document["id"], users["guest"].id)
    ).status_code == 204

    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 404
    rows = await db.execute(
        select(ActivityLog.action).where(ActivityLog.action == "guest.document_revoked")
    )
    assert len(list(rows.scalars())) == 1


# ---- folder-pinned: moving the document or deleting its folder revokes the grant ------------


async def test_moving_a_granted_document_revokes_the_grant(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    folder = await make_folder(client, member, ws, "F")
    document = await upload_document(
        client, storage, member, workspace_id=ws, folder_id=folder["id"]
    )
    await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    guest = users["guest"].headers
    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 200

    moved = await client.patch(
        f"{API}/documents/{document['id']}", json={"folder_id": None}, headers=member.headers
    )
    assert moved.status_code == 200

    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 404
    # re-granting after the move works normally
    assert (
        await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    ).status_code == 204
    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 200


async def test_deleting_a_granted_documents_folder_revokes_the_grant(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    folder = await make_folder(client, member, ws, "F")
    document = await upload_document(
        client, storage, member, workspace_id=ws, folder_id=folder["id"]
    )
    await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    guest = users["guest"].headers

    assert (
        await client.delete(f"{API}/folders/{folder['id']}", headers=member.headers)
    ).status_code == 204

    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 404
    # the document itself is fine, just moved to the root and ungranted
    still_there = await client.get(
        f"{API}/documents", params={"workspace_id": ws}, headers=member.headers
    )
    assert [d["id"] for d in still_there.json()["items"]] == [document["id"]]
    assert still_there.json()["items"][0]["folder_id"] is None


async def test_moving_the_containing_folder_itself_does_not_revoke(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    """Grants are pinned to the document's immediate folder, not its position in the tree: moving
    that folder somewhere else (without moving the document out of it) keeps the grant."""
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    a = await make_folder(client, member, ws, "A")
    b = await make_folder(client, member, ws, "B")
    document = await upload_document(client, storage, member, workspace_id=ws, folder_id=b["id"])
    await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    guest = users["guest"].headers

    moved = await client.patch(
        f"{API}/folders/{b['id']}", json={"parent_folder_id": a["id"]}, headers=member.headers
    )
    assert moved.status_code == 200

    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 200


async def test_restoring_a_deleted_document_into_a_gone_folder_revokes_the_grant(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    folder = await make_folder(client, member, ws, "F")
    document = await upload_document(
        client, storage, member, workspace_id=ws, folder_id=folder["id"]
    )
    await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    guest = users["guest"].headers

    await client.delete(f"{API}/documents/{document['id']}", headers=member.headers)
    await client.delete(f"{API}/folders/{folder['id']}", headers=member.headers)
    restored = await client.post(
        f"{API}/documents/{document['id']}/restore", headers=member.headers
    )
    assert restored.status_code == 200 and restored.json()["folder_id"] is None

    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 404


async def test_restoring_a_deleted_document_whose_folder_is_untouched_keeps_the_grant(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    folder = await make_folder(client, member, ws, "F")
    document = await upload_document(
        client, storage, member, workspace_id=ws, folder_id=folder["id"]
    )
    await grant(client, users["admin"].headers, document["id"], users["guest"].id)
    guest = users["guest"].headers

    await client.delete(f"{API}/documents/{document['id']}", headers=member.headers)
    restored = await client.post(
        f"{API}/documents/{document['id']}/restore", headers=member.headers
    )
    assert restored.status_code == 200 and restored.json()["folder_id"] == folder["id"]

    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=guest)
    ).status_code == 200
