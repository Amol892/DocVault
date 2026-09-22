"""Trash and restore (FR-7), version history (FR-8), moving folders (FR-22), and the purge job."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.enums import UploadStatus
from app.services.purge import purge
from tests.fake_storage import FakeStorage
from tests.helpers import (
    API,
    make_folder,
    make_user,
    upload_document,
    workspace_with_roles,
)

# ---- trash and restore -----------------------------------------------------------------------


async def test_deleted_document_is_in_the_trash_and_can_be_restored(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    document = await upload_document(client, storage, member, workspace_id=ws)
    await client.delete(f"{API}/documents/{document['id']}", headers=member.headers)

    trash = await client.get(
        f"{API}/documents/trash", params={"workspace_id": ws}, headers=member.headers
    )
    assert [d["id"] for d in trash.json()["items"]] == [document["id"]]
    live = await client.get(f"{API}/documents", params={"workspace_id": ws}, headers=member.headers)
    assert live.json()["total"] == 0

    restored = await client.post(
        f"{API}/documents/{document['id']}/restore", headers=member.headers
    )
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None
    live = await client.get(f"{API}/documents", params={"workspace_id": ws}, headers=member.headers)
    assert live.json()["total"] == 1
    trash = await client.get(
        f"{API}/documents/trash", params={"workspace_id": ws}, headers=member.headers
    )
    assert trash.json()["total"] == 0


async def test_restoring_into_a_deleted_folder_lands_at_the_root(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    folder = await make_folder(client, member, ws, "Temp")
    document = await upload_document(
        client, storage, member, workspace_id=ws, folder_id=folder["id"]
    )
    await client.delete(f"{API}/documents/{document['id']}", headers=member.headers)
    await client.delete(f"{API}/folders/{folder['id']}", headers=member.headers)

    restored = await client.post(
        f"{API}/documents/{document['id']}/restore", headers=member.headers
    )
    assert restored.status_code == 200
    assert restored.json()["folder_id"] is None


async def test_restore_after_the_grace_period_is_404(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    document = await upload_document(client, storage, member, workspace_id=ws)
    await client.delete(f"{API}/documents/{document['id']}", headers=member.headers)
    await db.execute(
        update(Document)
        .where(Document.id == document["id"])
        .values(deleted_at=datetime.now(UTC) - timedelta(days=31))
    )
    await db.commit()

    trash = await client.get(
        f"{API}/documents/trash", params={"workspace_id": ws}, headers=member.headers
    )
    assert trash.json()["total"] == 0
    response = await client.post(
        f"{API}/documents/{document['id']}/restore", headers=member.headers
    )
    assert response.status_code == 404


async def test_trash_and_restore_access_rules(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    document = await upload_document(client, storage, users["member"], workspace_id=ws)
    personal = await upload_document(client, storage, users["member"], filename="mine.pdf")
    for item in (document, personal):
        await client.delete(f"{API}/documents/{item['id']}", headers=users["member"].headers)

    params = {"workspace_id": ws}
    assert (
        await client.get(f"{API}/documents/trash", params=params, headers=users["guest"].headers)
    ).status_code == 403
    assert (
        await client.get(f"{API}/documents/trash", params=params, headers=users["outsider"].headers)
    ).status_code == 404
    assert (await client.get(f"{API}/documents/trash")).status_code == 401

    # anyone who cannot see a trashed document gets the same 404 as for a missing one
    missing = await client.post(
        f"{API}/documents/doesnotexist1/restore", headers=users["outsider"].headers
    )
    for actor, target in [
        (users["outsider"], document["id"]),
        (users["owner"], personal["id"]),  # someone else's personal document
    ]:
        response = await client.post(f"{API}/documents/{target}/restore", headers=actor.headers)
        assert response.status_code == 404 and response.json() == missing.json()
    guest = await client.post(
        f"{API}/documents/{document['id']}/restore", headers=users["guest"].headers
    )
    assert guest.status_code in (403, 404)

    # a personal document's trash belongs to its owner alone
    own = await client.get(f"{API}/documents/trash", headers=users["member"].headers)
    assert [d["id"] for d in own.json()["items"]] == [personal["id"]]
    other = await client.get(f"{API}/documents/trash", headers=users["owner"].headers)
    assert other.json()["total"] == 0


async def test_restoring_a_live_document_is_404(client: AsyncClient, storage: FakeStorage) -> None:
    user = await make_user(client, "me@example.com")
    document = await upload_document(client, storage, user)
    response = await client.post(f"{API}/documents/{document['id']}/restore", headers=user.headers)
    assert response.status_code == 404


# ---- versions --------------------------------------------------------------------------------


async def test_version_history_and_old_version_download(
    client: AsyncClient, storage: FakeStorage
) -> None:
    user = await make_user(client, "me@example.com")
    first = await upload_document(client, storage, user)
    await upload_document(
        client, storage, user, document_id=first["id"], data=b"%PDF-1.7\nsecond version body\n"
    )
    versions = await client.get(f"{API}/documents/{first['id']}/versions", headers=user.headers)
    body = versions.json()
    assert [v["version_number"] for v in body] == [2, 1]
    assert [v["is_current"] for v in body] == [True, False]
    assert body[0]["created_by_name"] == user.name

    old = await client.get(
        f"{API}/documents/{first['id']}/versions/1/download-url", headers=user.headers
    )
    assert old.status_code == 200 and old.json()["download_url"].split("?")[0].endswith("/1")
    missing = await client.get(
        f"{API}/documents/{first['id']}/versions/9/download-url", headers=user.headers
    )
    assert missing.status_code == 404


async def test_version_endpoints_hide_documents_from_outsiders(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    for path in (
        f"/documents/{document['id']}/versions",
        f"/documents/{document['id']}/versions/1/download-url",
    ):
        response = await client.get(f"{API}{path}", headers=users["outsider"].headers)
        assert response.status_code == 404
        assert (await client.get(f"{API}{path}")).status_code == 401


# ---- moving folders --------------------------------------------------------------------------


async def test_move_a_folder_with_its_contents(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    a = await make_folder(client, member, ws, "A")
    b = await make_folder(client, member, ws, "B")
    child = await make_folder(client, member, ws, "Child", b["id"])

    moved = await client.patch(
        f"{API}/folders/{b['id']}", json={"parent_folder_id": a["id"]}, headers=member.headers
    )
    assert moved.status_code == 200 and moved.json()["parent_folder_id"] == a["id"]
    listed = (await client.get(f"{API}/workspaces/{ws}/folders", headers=member.headers)).json()
    parents = {f["id"]: f["parent_folder_id"] for f in listed}
    assert parents[child["id"]] == b["id"]  # its subtree came along

    back = await client.patch(
        f"{API}/folders/{b['id']}", json={"parent_folder_id": None}, headers=member.headers
    )
    assert back.json()["parent_folder_id"] is None


async def test_a_folder_cannot_move_into_itself_or_its_descendants(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    top = await make_folder(client, member, ws, "Top")
    leaf = await make_folder(client, member, ws, "Leaf", top["id"])
    for target in (top["id"], leaf["id"]):
        response = await client.patch(
            f"{API}/folders/{top['id']}", json={"parent_folder_id": target}, headers=member.headers
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FOLDER_CYCLE"


async def test_move_respects_name_clashes_depth_and_workspace_boundaries(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    a = await make_folder(client, member, ws, "A")
    await make_folder(client, member, ws, "Same", a["id"])
    other_same = await make_folder(client, member, ws, "same")
    clash = await client.patch(
        f"{API}/folders/{other_same['id']}",
        json={"parent_folder_id": a["id"]},
        headers=member.headers,
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "NAME_TAKEN"

    # a 20-level tree (the maximum) cannot be put under another folder
    parent: str | None = None
    for level in range(20):
        parent = (await make_folder(client, member, ws, f"D{level}", parent))["id"]
    root_of_chain = (
        await client.get(f"{API}/workspaces/{ws}/folders", headers=member.headers)
    ).json()
    chain_root = next(f for f in root_of_chain if f["name"] == "D0")
    too_deep = await client.patch(
        f"{API}/folders/{chain_root['id']}",
        json={"parent_folder_id": a["id"]},
        headers=member.headers,
    )
    assert too_deep.status_code == 422 and too_deep.json()["error"]["code"] == "FOLDER_TOO_DEEP"

    outsider_ws = (
        await client.post(
            f"{API}/workspaces", json={"name": "Elsewhere"}, headers=users["outsider"].headers
        )
    ).json()
    foreign = await make_folder(client, users["outsider"], outsider_ws["id"], "Foreign")
    cross = await client.patch(
        f"{API}/folders/{a['id']}", json={"parent_folder_id": foreign["id"]}, headers=member.headers
    )
    assert cross.status_code == 404


async def test_folder_patch_needs_exactly_one_field_and_guests_cannot_move(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member, ws = users["member"], workspace["id"]
    folder = await make_folder(client, member, ws, "F")
    for body in ({}, {"name": "x", "parent_folder_id": None}, {"name": None}):
        response = await client.patch(
            f"{API}/folders/{folder['id']}", json=body, headers=member.headers
        )
        assert response.status_code == 422
    # a Guest has no standing on any folder at all (FR-21: access is per document) — 404
    guest = await client.patch(
        f"{API}/folders/{folder['id']}",
        json={"parent_folder_id": None},
        headers=users["guest"].headers,
    )
    assert guest.status_code == 404


# ---- purge job -------------------------------------------------------------------------------


async def test_purge_removes_expired_trash_stale_uploads_and_keeps_the_rest(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    user = await make_user(client, "me@example.com")
    old = await upload_document(client, storage, user, filename="old.pdf")
    recent = await upload_document(client, storage, user, filename="recent.pdf")
    keep = await upload_document(client, storage, user, filename="keep.pdf")
    for item in (old, recent):
        await client.delete(f"{API}/documents/{item['id']}", headers=user.headers)
    await db.execute(
        update(Document)
        .where(Document.id == old["id"])
        .values(deleted_at=datetime.now(UTC) - timedelta(days=45))
    )
    # an upload that was requested (and maybe put) but never confirmed, a day and a bit ago
    abandoned = (
        await client.post(
            f"{API}/documents/upload-url",
            json={"filename": "ghost.pdf", "mime_type": "application/pdf", "size_bytes": 10},
            headers=user.headers,
        )
    ).json()
    storage.put(abandoned["upload_url"], b"%PDF-1.7\n12")
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.document_id == abandoned["document_id"])
        .values(created_at=datetime.now(UTC) - timedelta(hours=30))
    )
    await db.commit()
    old_keys = [k for k in storage.objects if f"/{old['id']}/" in k]
    assert old_keys

    report = await purge(db, storage)

    assert report.documents == 1 and report.stale_uploads == 1
    assert not [k for k in storage.objects if f"/{old['id']}/" in k]
    assert abandoned["storage_key"] not in storage.objects
    db.expire_all()
    remaining = set((await db.execute(select(Document.id))).scalars())
    assert old["id"] not in remaining
    assert {recent["id"], keep["id"], abandoned["document_id"]} <= remaining
    ghost = (
        await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == abandoned["document_id"])
        )
    ).scalar_one()
    assert ghost.upload_status == UploadStatus.REJECTED
    # the abandoned document has no usable file, so it is now in line for removal too
    ghost_doc = await db.get(Document, abandoned["document_id"])
    assert ghost_doc is not None and ghost_doc.deleted_at is not None
    # untouched documents still list, and the second run finds nothing to do
    listed = await client.get(f"{API}/documents", headers=user.headers)
    assert [d["id"] for d in listed.json()["items"]] == [keep["id"]]
    again = await purge(db, storage)
    assert (again.documents, again.stale_uploads) == (0, 0)
