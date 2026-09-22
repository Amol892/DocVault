"""In-app inline preview for logged-in users (PDF/images/plain text), separate from download."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fake_storage import FakeStorage
from tests.helpers import API, make_user, upload_document, workspace_with_roles


async def test_a_previewable_document_returns_an_inline_url(
    client: AsyncClient, storage: FakeStorage
) -> None:
    user = await make_user(client, "me@example.com")
    document = await upload_document(client, storage, user)  # a PDF, per the helper's default
    response = await client.get(
        f"{API}/documents/{document['id']}/preview-url", headers=user.headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 300
    assert "inline" in body["preview_url"]
    assert "attachment" not in body["preview_url"]


async def test_a_non_previewable_type_is_refused(client: AsyncClient, storage: FakeStorage) -> None:
    user = await make_user(client, "me@example.com")
    document = await upload_document(
        client,
        storage,
        user,
        filename="a.zip",
        mime_type="application/zip",
        data=b"PK\x03\x04" + b"\x00" * 20,
    )
    response = await client.get(
        f"{API}/documents/{document['id']}/preview-url", headers=user.headers
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "NOT_PREVIEWABLE"


async def test_preview_serves_the_current_version(
    client: AsyncClient, storage: FakeStorage
) -> None:
    user = await make_user(client, "me@example.com")
    document = await upload_document(client, storage, user)
    v2 = await upload_document(
        client, storage, user, document_id=document["id"], data=b"%PDF-1.7\nsecond\n"
    )
    assert v2["id"] == document["id"]
    response = await client.get(
        f"{API}/documents/{document['id']}/preview-url", headers=user.headers
    )
    assert response.json()["preview_url"].split("?")[0].endswith("/2")


async def test_preview_respects_document_access(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    outsider = await client.get(
        f"{API}/documents/{document['id']}/preview-url", headers=users["outsider"].headers
    )
    assert outsider.status_code == 404

    guest_blind = await client.get(
        f"{API}/documents/{document['id']}/preview-url", headers=users["guest"].headers
    )
    assert guest_blind.status_code == 404

    await client.post(
        f"{API}/documents/{document['id']}/grants",
        json={"user_id": users["guest"].id},
        headers=users["admin"].headers,
    )
    guest_ok = await client.get(
        f"{API}/documents/{document['id']}/preview-url", headers=users["guest"].headers
    )
    assert guest_ok.status_code == 200


async def test_preview_needs_a_token(client: AsyncClient) -> None:
    response = await client.get(f"{API}/documents/x/preview-url")
    assert response.status_code == 401
