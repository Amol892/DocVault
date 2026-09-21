"""Documents: upload (with versions), confirm, list/search, download, rename, move, delete."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document import DocumentVersion
from app.models.enums import UploadStatus
from tests.fake_storage import FakeStorage
from tests.helpers import (
    API,
    PDF,
    make_folder,
    make_user,
    upload_document,
    workspace_with_roles,
)


async def request_upload(client: AsyncClient, user: Any, **overrides: Any) -> Any:
    body = {
        "filename": "report.pdf",
        "mime_type": "application/pdf",
        "size_bytes": len(PDF),
        "workspace_id": None,
        "folder_id": None,
        **overrides,
    }
    return await client.post(f"{API}/documents/upload-url", json=body, headers=user.headers)


# ---- upload URL ----------------------------------------------------------------------------


async def test_upload_url_creates_a_pending_document(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    response = await request_upload(client, users["member"], workspace_id=workspace["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["storage_key"] == f"w/{workspace['id']}/{body['document_id']}/1"
    assert "report" not in body["storage_key"]  # never derived from the filename
    assert body["upload_url"].startswith("http://storage.test/")

    # a document with no ready version is not listed yet
    listed = await client.get(
        f"{API}/documents",
        params={"workspace_id": workspace["id"]},
        headers=users["member"].headers,
    )
    assert listed.json()["total"] == 0
    version = (await db.execute(select(DocumentVersion))).scalar_one()
    assert version.upload_status == UploadStatus.PENDING
    assert version.storage_url.endswith(body["storage_key"])


async def test_personal_upload_key(client: AsyncClient) -> None:
    user = await make_user(client, "me@example.com")
    body = (await request_upload(client, user)).json()
    assert body["storage_key"] == f"u/{user.id}/{body['document_id']}/1"


async def test_size_limit(client: AsyncClient) -> None:
    limit = get_settings().max_upload_mb * 1024 * 1024
    user = await make_user(client, "me@example.com")
    response = await request_upload(client, user, size_bytes=limit + 1)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert (await request_upload(client, user, size_bytes=limit)).status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"filename": ""},
        {"filename": "a/b.pdf"},
        {"filename": "..\\evil.pdf"},
        {"mime_type": "notamime"},
        {"mime_type": ""},
        {"size_bytes": 0},
        {"size_bytes": -5},
    ],
)
async def test_upload_validation_errors(client: AsyncClient, overrides: dict[str, Any]) -> None:
    user = await make_user(client, "me@example.com")
    assert (await request_upload(client, user, **overrides)).status_code == 422


async def test_guest_cannot_upload_and_outsider_gets_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    guest = await request_upload(client, users["guest"], workspace_id=workspace["id"])
    assert guest.status_code == 403
    outsider = await request_upload(client, users["outsider"], workspace_id=workspace["id"])
    assert outsider.status_code == 404


async def test_upload_into_a_bad_folder_is_404(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    response = await request_upload(
        client, users["member"], workspace_id=workspace["id"], folder_id="missing"
    )
    assert response.status_code == 404
    # personal documents have no folders
    mine = await request_upload(client, users["member"], folder_id="anything")
    assert mine.status_code == 404


# ---- confirm -------------------------------------------------------------------------------


async def test_confirm_makes_the_document_listable(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    folder = await make_folder(client, users["member"], workspace["id"], "Docs")
    document = await upload_document(
        client, storage, users["member"], workspace_id=workspace["id"], folder_id=folder["id"]
    )
    assert document["filename"] == "report.pdf"
    assert document["mime_type"] == "application/pdf"
    assert document["size_bytes"] == len(PDF)
    assert document["owner_name"] == users["member"].name
    assert document["folder_id"] == folder["id"]
    assert document["visibility"] == "workspace"

    listed = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=users["owner"].headers
    )
    assert [d["id"] for d in listed.json()["items"]] == [document["id"]]


async def test_confirm_without_upload_is_409(client: AsyncClient) -> None:
    user = await make_user(client, "me@example.com")
    granted = (await request_upload(client, user)).json()
    response = await client.post(
        f"{API}/documents/{granted['document_id']}/confirm-upload", headers=user.headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"


async def test_confirm_is_idempotent(client: AsyncClient, storage: FakeStorage) -> None:
    user = await make_user(client, "me@example.com")
    document = await upload_document(client, storage, user)
    again = await client.post(
        f"{API}/documents/{document['id']}/confirm-upload", headers=user.headers
    )
    assert again.status_code == 200
    assert again.json()["id"] == document["id"]


async def _rejected(
    client: AsyncClient,
    storage: FakeStorage,
    db: AsyncSession,
    *,
    data: bytes,
    stored_type: str | None = None,
    declared_size: int | None = None,
    mime_type: str = "application/pdf",
) -> tuple[Any, str]:
    user = await make_user(client, "me@example.com")
    granted = (
        await request_upload(
            client, user, mime_type=mime_type, size_bytes=declared_size or len(data)
        )
    ).json()
    storage.put(granted["upload_url"], data, stored_type)
    response = await client.post(
        f"{API}/documents/{granted['document_id']}/confirm-upload", headers=user.headers
    )
    return response, granted["storage_key"]


async def test_wrong_size_is_rejected_and_cleaned_up(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    response, key = await _rejected(client, storage, db, data=PDF, declared_size=len(PDF) + 10)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UPLOAD_REJECTED"
    assert key in storage.deleted and key not in storage.objects
    version = (await db.execute(select(DocumentVersion))).scalar_one()
    assert version.upload_status == UploadStatus.REJECTED


async def test_wrong_content_type_is_rejected(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    response, _ = await _rejected(client, storage, db, data=PDF, stored_type="text/plain")
    assert response.status_code == 422


async def test_pdf_claim_with_other_bytes_is_rejected(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    response, _ = await _rejected(client, storage, db, data=b"just some text, no pdf here")
    assert response.status_code == 422
    assert "PDF" in response.json()["error"]["message"]


async def test_executable_is_rejected_whatever_it_claims(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    elf = b"\x7fELF" + b"\x00" * 60
    response, _ = await _rejected(
        client, storage, db, data=elf, mime_type="application/octet-stream"
    )
    assert response.status_code == 422
    assert "Executable" in response.json()["error"]["message"]


async def test_rejected_document_does_not_appear_anywhere(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    await _rejected(client, storage, db, data=b"nope")
    user = await make_user(client, "other@example.com")
    listed = await client.get(f"{API}/documents", headers=user.headers)
    assert listed.json()["total"] == 0


# ---- versions ------------------------------------------------------------------------------


async def test_new_version_replaces_the_current_file(
    client: AsyncClient, storage: FakeStorage, db: AsyncSession
) -> None:
    user = await make_user(client, "me@example.com")
    first = await upload_document(client, storage, user)
    second_bytes = b"%PDF-1.7\nsecond and longer version\n"
    second = await upload_document(
        client, storage, user, document_id=first["id"], data=second_bytes
    )
    assert second["id"] == first["id"]
    assert second["size_bytes"] == len(second_bytes)

    versions = (
        await db.execute(select(DocumentVersion).order_by(DocumentVersion.version_number))
    ).scalars()
    assert [v.version_number for v in versions] == [1, 2]

    url = (
        await client.get(f"{API}/documents/{first['id']}/download-url", headers=user.headers)
    ).json()
    assert url["download_url"].rstrip().split("?")[0].endswith("/2")


async def test_pending_new_version_does_not_hide_the_current_file(
    client: AsyncClient, storage: FakeStorage
) -> None:
    user = await make_user(client, "me@example.com")
    first = await upload_document(client, storage, user)
    await request_upload(client, user, document_id=first["id"])  # requested but never uploaded

    listed = await client.get(f"{API}/documents", headers=user.headers)
    assert [d["id"] for d in listed.json()["items"]] == [first["id"]]
    url = await client.get(f"{API}/documents/{first['id']}/download-url", headers=user.headers)
    assert url.status_code == 200
    assert url.json()["download_url"].split("?")[0].endswith("/1")


# ---- list / search -------------------------------------------------------------------------


async def test_list_filters_by_folder_and_paginates(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member = users["member"]
    folder = await make_folder(client, member, workspace["id"], "F")
    inside = await upload_document(
        client,
        storage,
        member,
        workspace_id=workspace["id"],
        folder_id=folder["id"],
        filename="in.pdf",
    )
    await upload_document(
        client, storage, member, workspace_id=workspace["id"], filename="root.pdf"
    )

    in_folder = await client.get(
        f"{API}/documents",
        params={"workspace_id": workspace["id"], "folder_id": folder["id"]},
        headers=member.headers,
    )
    assert [d["id"] for d in in_folder.json()["items"]] == [inside["id"]]
    everything = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=member.headers
    )
    assert everything.json()["total"] == 2 and everything.json()["page"] == 1
    page_two = await client.get(
        f"{API}/documents",
        params={"workspace_id": workspace["id"], "page": 2},
        headers=member.headers,
    )
    assert page_two.json()["items"] == [] and page_two.json()["total"] == 2
    assert (
        await client.get(f"{API}/documents", params={"page": 0}, headers=member.headers)
    ).status_code == 422


async def test_search_matches_filename_or_uploader_and_escapes_wildcards(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    await upload_document(
        client, storage, users["member"], workspace_id=ws, filename="Budget 2026.pdf"
    )
    await upload_document(
        client, storage, users["admin"], workspace_id=ws, filename="100%_done.pdf"
    )
    await upload_document(client, storage, users["admin"], workspace_id=ws, filename="other.pdf")

    async def search(q: str) -> list[str]:
        response = await client.get(
            f"{API}/documents", params={"workspace_id": ws, "q": q}, headers=users["owner"].headers
        )
        assert response.status_code == 200
        return sorted(d["filename"] for d in response.json()["items"])

    assert await search("budget") == ["Budget 2026.pdf"]
    assert await search("MEMBER") == ["Budget 2026.pdf"]  # uploader name
    assert await search("Admin") == ["100%_done.pdf", "other.pdf"]
    assert await search("%") == ["100%_done.pdf"]  # not a wildcard
    assert await search("_") == ["100%_done.pdf"]
    assert await search("zzz") == []


async def test_personal_documents_are_listed_only_for_their_owner(
    client: AsyncClient, storage: FakeStorage
) -> None:
    alice = await make_user(client, "alice@example.com")
    bob = await make_user(client, "bob@example.com")
    mine = await upload_document(client, storage, alice)
    assert mine["workspace_id"] is None and mine["visibility"] == "private"
    assert (await client.get(f"{API}/documents", headers=alice.headers)).json()["total"] == 1
    assert (await client.get(f"{API}/documents", headers=bob.headers)).json()["total"] == 0


async def test_list_for_a_foreign_workspace_or_folder_is_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    outsider = users["outsider"].headers
    listed = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=outsider
    )
    assert listed.status_code == 404
    bogus = await client.get(
        f"{API}/documents",
        params={"workspace_id": workspace["id"], "folder_id": "nope"},
        headers=users["owner"].headers,
    )
    assert bogus.status_code == 404


# ---- download ------------------------------------------------------------------------------


async def test_download_url_forces_attachment(client: AsyncClient, storage: FakeStorage) -> None:
    user = await make_user(client, "me@example.com")
    document = await upload_document(client, storage, user, filename='evil"; name.pdf')
    response = await client.get(
        f"{API}/documents/{document['id']}/download-url", headers=user.headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 300
    assert "attachment" in body["download_url"].replace("%20", " ").replace("%3B", ";")


# ---- rename / move / delete ----------------------------------------------------------------


async def test_rename_and_move(client: AsyncClient, db: AsyncSession, storage: FakeStorage) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member = users["member"]
    folder = await make_folder(client, member, workspace["id"], "Target")
    document = await upload_document(client, storage, member, workspace_id=workspace["id"])

    renamed = await client.patch(
        f"{API}/documents/{document['id']}",
        json={"filename": "new name.pdf"},
        headers=member.headers,
    )
    assert renamed.status_code == 200 and renamed.json()["filename"] == "new name.pdf"

    moved = await client.patch(
        f"{API}/documents/{document['id']}",
        json={"folder_id": folder["id"]},
        headers=member.headers,
    )
    assert moved.json()["folder_id"] == folder["id"]
    back = await client.patch(
        f"{API}/documents/{document['id']}", json={"folder_id": None}, headers=member.headers
    )
    assert back.json()["folder_id"] is None


@pytest.mark.parametrize(
    "body",
    [{}, {"filename": "a.pdf", "folder_id": None}, {"filename": None}, {"filename": "a/b"}],
)
async def test_patch_needs_exactly_one_valid_field(
    client: AsyncClient, storage: FakeStorage, body: dict[str, Any]
) -> None:
    user = await make_user(client, "me@example.com")
    document = await upload_document(client, storage, user)
    response = await client.patch(
        f"{API}/documents/{document['id']}", json=body, headers=user.headers
    )
    assert response.status_code == 422


async def test_move_to_another_workspaces_folder_is_404(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    other_owner = await make_user(client, "other-owner@example.com")
    from tests.helpers import make_workspace

    other = await make_workspace(client, other_owner, "Other")
    foreign = await make_folder(client, other_owner, other["id"], "Foreign")
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    response = await client.patch(
        f"{API}/documents/{document['id']}",
        json={"folder_id": foreign["id"]},
        headers=users["member"].headers,
    )
    assert response.status_code == 404


async def test_delete_is_soft_and_hides_the_document(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    member = users["member"]
    document = await upload_document(client, storage, member, workspace_id=workspace["id"])
    assert (
        await client.delete(f"{API}/documents/{document['id']}", headers=member.headers)
    ).status_code == 204

    listed = await client.get(
        f"{API}/documents", params={"workspace_id": workspace["id"]}, headers=member.headers
    )
    assert listed.json()["total"] == 0
    assert (
        await client.get(f"{API}/documents/{document['id']}/download-url", headers=member.headers)
    ).status_code == 404
    assert (
        await client.delete(f"{API}/documents/{document['id']}", headers=member.headers)
    ).status_code == 404
    # nothing was destroyed: the row and its object are still there for the grace period
    assert storage.objects
    assert (
        await db.execute(select(DocumentVersion))
    ).scalar_one().upload_status == UploadStatus.READY
