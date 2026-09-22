"""Share links (FR-10..15): management by the owner side, and the public no-account path."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from app.models.document import Document
from app.models.share_link import ShareLink, ShareLinkAccessLog
from app.services.share_links import MAX_BAD_PASSWORDS
from tests.fake_storage import FakeStorage
from tests.helpers import (
    API,
    TestUser,
    make_user,
    make_workspace,
    upload_document,
    workspace_with_roles,
)


async def create_link(
    client: AsyncClient, user: TestUser, document_id: str, **body: Any
) -> Response:
    return await client.post(
        f"{API}/documents/{document_id}/share-links", json=body, headers=user.headers
    )


def token_of(url: str) -> str:
    return url.rsplit("/s/", 1)[1]


async def open_link(
    client: AsyncClient, token: str, password: str | None = None, **headers: str
) -> Response:
    return await client.post(
        f"{API}/public/share/{token}/access", json={"password": password}, headers=headers
    )


async def shared_document(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage, **link: Any
) -> tuple[dict[str, Any], dict[str, TestUser], dict[str, Any], str]:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    created = await create_link(client, users["member"], document["id"], **link)
    assert created.status_code == 201, created.text
    return document, users, created.json(), token_of(created.json()["url"])


# ---- management ------------------------------------------------------------------------------


async def test_create_list_and_visibility(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, link, token = await shared_document(client, db, storage)
    assert link["url"].endswith(f"/s/{token}")
    assert len(token) >= 43  # 32 random bytes, base64url: 256 bits
    assert link["allow_download"] is True and link["has_password"] is False
    assert link["expires_at"] is None and link["revoked_at"] is None and link["expired"] is False

    listed = await client.get(
        f"{API}/documents/{document['id']}/share-links", headers=users["admin"].headers
    )
    assert [item["id"] for item in listed.json()] == [link["id"]]
    assert "url" not in listed.json()[0] or listed.json()[0]["url"] is None  # never shown again

    docs = await client.get(
        f"{API}/documents",
        params={"workspace_id": document["workspace_id"]},
        headers=users["member"].headers,
    )
    assert docs.json()["items"][0]["visibility"] == "public"


async def test_only_the_hash_of_the_token_is_stored(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    _, _, link, token = await shared_document(client, db, storage, password="secret-pass")
    row = (await db.execute(select(ShareLink).where(ShareLink.id == link["id"]))).scalar_one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in row.token_hash
    assert row.password_hash is not None and "secret-pass" not in row.password_hash
    assert link["has_password"] is True


async def test_personal_documents_can_be_shared_by_their_owner_only(
    client: AsyncClient, storage: FakeStorage
) -> None:
    alice = await make_user(client, "alice@example.com")
    bob = await make_user(client, "bob@example.com")
    document = await upload_document(client, storage, alice)
    assert (await create_link(client, bob, document["id"])).status_code == 404
    created = await create_link(client, alice, document["id"])
    assert created.status_code == 201
    listed = await client.get(f"{API}/documents", headers=alice.headers)
    assert listed.json()["items"][0]["visibility"] == "public"


async def test_who_may_manage_links(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, link, _ = await shared_document(client, db, storage)
    guest_doc = await upload_document(
        client, storage, users["member"], workspace_id=document["workspace_id"]
    )
    await client.post(
        f"{API}/documents/{guest_doc['id']}/grants",
        json={"user_id": users["guest"].id},
        headers=users["admin"].headers,
    )
    guest = users["guest"]
    # a guest who can read the document still can never share it
    assert (await create_link(client, guest, guest_doc["id"])).status_code == 403
    assert (
        await client.get(f"{API}/documents/{guest_doc['id']}/share-links", headers=guest.headers)
    ).status_code == 403
    assert (
        await client.delete(f"{API}/share-links/{link['id']}", headers=guest.headers)
    ).status_code in (
        403,
        404,
    )
    # nobody outside the workspace can tell the document or link exists
    missing_doc = await create_link(client, users["outsider"], "doesnotexist1")
    real_doc = await create_link(client, users["outsider"], document["id"])
    assert real_doc.status_code == 404 and real_doc.json() == missing_doc.json()
    missing_link = await client.delete(
        f"{API}/share-links/doesnotexist1", headers=users["outsider"].headers
    )
    real_link = await client.delete(
        f"{API}/share-links/{link['id']}", headers=users["outsider"].headers
    )
    assert real_link.status_code == 404 and real_link.json() == missing_link.json()
    other_owner = await make_user(client, "other-owner@example.com")
    await make_workspace(client, other_owner, "Elsewhere")
    assert (await create_link(client, other_owner, document["id"])).status_code == 404
    # and anonymous callers are turned away
    for method, path in [
        ("POST", f"/documents/{document['id']}/share-links"),
        ("GET", f"/documents/{document['id']}/share-links"),
        ("DELETE", f"/share-links/{link['id']}"),
        ("GET", f"/share-links/{link['id']}/access-log"),
    ]:
        assert (await client.request(method, f"{API}{path}")).status_code == 401


async def test_create_validation(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    document = await upload_document(client, storage, users["member"], workspace_id=workspace["id"])
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    assert (
        await create_link(client, users["member"], document["id"], expires_at=past)
    ).status_code == 422
    assert (
        await create_link(client, users["member"], document["id"], password="abc")
    ).status_code == 422
    ok = await create_link(
        client, users["member"], document["id"], expires_at=future, password="abcd"
    )
    assert ok.status_code == 201 and ok.json()["expires_at"] is not None


async def test_allow_download_can_be_edited_without_changing_the_address(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, link, token = await shared_document(client, db, storage)
    assert link["allow_download"] is True

    opened = await open_link(client, token)
    assert opened.json()["download_url"] is not None

    patched = await client.patch(
        f"{API}/share-links/{link['id']}",
        json={"allow_download": False},
        headers=users["member"].headers,
    )
    assert patched.status_code == 200
    assert patched.json()["allow_download"] is False
    assert patched.json().get("url") is None  # a patch never reveals the address either

    reopened = await open_link(client, token)
    assert reopened.status_code == 200  # the same link, same token, still works
    assert reopened.json()["download_url"] is None
    assert (
        reopened.json()["preview_url"] is not None
    )  # a PDF: still viewable, just not downloadable

    back_on = await client.patch(
        f"{API}/share-links/{link['id']}",
        json={"allow_download": True},
        headers=users["member"].headers,
    )
    assert back_on.status_code == 200 and back_on.json()["allow_download"] is True
    assert (await open_link(client, token)).json()["download_url"] is not None


async def test_updating_a_share_link_is_logged_and_gated_like_creating_one(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, link, _ = await shared_document(client, db, storage)
    await client.post(
        f"{API}/documents/{document['id']}/grants",
        json={"user_id": users["guest"].id},
        headers=users["admin"].headers,
    )
    assert (
        await client.patch(
            f"{API}/share-links/{link['id']}",
            json={"allow_download": False},
            headers=users["guest"].headers,
        )
    ).status_code == 403
    assert (
        await client.patch(
            f"{API}/share-links/{link['id']}",
            json={"allow_download": False},
            headers=users["outsider"].headers,
        )
    ).status_code == 404
    assert (
        await client.patch(f"{API}/share-links/{link['id']}", json={"allow_download": False})
    ).status_code == 401

    await client.patch(
        f"{API}/share-links/{link['id']}",
        json={"allow_download": False},
        headers=users["member"].headers,
    )
    updated = (
        await client.get(
            f"{API}/share-links/{link['id']}/access-log", headers=users["member"].headers
        )
    ).status_code
    assert updated == 200  # the endpoint stays reachable; the real check is the activity row below
    actions = (
        await db.execute(
            select(ActivityLog.action).where(ActivityLog.action == "share_link.updated")
        )
    ).scalars()
    assert len(list(actions)) == 1

    # setting it to the value it already has is a no-op: nothing new logged
    await client.patch(
        f"{API}/share-links/{link['id']}",
        json={"allow_download": False},
        headers=users["member"].headers,
    )
    actions_again = (
        await db.execute(
            select(ActivityLog.action).where(ActivityLog.action == "share_link.updated")
        )
    ).scalars()
    assert len(list(actions_again)) == 1


async def test_revoking_is_idempotent_and_ends_public_visibility(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, link, token = await shared_document(client, db, storage)
    assert (await open_link(client, token)).status_code == 200

    for _ in range(2):
        response = await client.delete(
            f"{API}/share-links/{link['id']}", headers=users["member"].headers
        )
        assert response.status_code == 204

    gone = await open_link(client, token)  # effective on the very next access, no caching
    assert gone.status_code == 410 and gone.json()["error"]["code"] == "LINK_REVOKED"
    listed = await client.get(
        f"{API}/documents/{document['id']}/share-links", headers=users["member"].headers
    )
    assert listed.json()[0]["revoked_at"] is not None
    docs = await client.get(
        f"{API}/documents",
        params={"workspace_id": document["workspace_id"]},
        headers=users["member"].headers,
    )
    assert docs.json()["items"][0]["visibility"] == "workspace"
    actions = (
        await db.execute(select(ActivityLog.action).where(ActivityLog.action.like("share_link.%")))
    ).scalars()
    assert sorted(actions) == ["share_link.created", "share_link.revoked"]


async def test_an_expired_link_is_not_public_and_reports_expired(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, link, token = await shared_document(
        client, db, storage, expires_at=(datetime.now(UTC) + timedelta(days=1)).isoformat()
    )
    await db.execute(
        update(ShareLink)
        .where(ShareLink.id == link["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db.commit()
    listed = await client.get(
        f"{API}/documents/{document['id']}/share-links", headers=users["member"].headers
    )
    assert listed.json()[0]["expired"] is True
    docs = await client.get(
        f"{API}/documents",
        params={"workspace_id": document["workspace_id"]},
        headers=users["member"].headers,
    )
    assert docs.json()["items"][0]["visibility"] == "workspace"
    response = await open_link(client, token)
    assert response.status_code == 410 and response.json()["error"]["code"] == "LINK_EXPIRED"


# ---- public access ---------------------------------------------------------------------------


async def test_a_recipient_needs_no_account_and_gets_only_that_document(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    _, _, _, token = await shared_document(client, db, storage)
    response = await open_link(client, token)  # no Authorization header at all
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "requires_password",
        "filename",
        "mime_type",
        "size_bytes",
        "allow_download",
        "expires_at",
        "download_url",
        "preview_url",
    }
    assert body["filename"] == "report.pdf" and body["mime_type"] == "application/pdf"
    assert body["requires_password"] is False and body["allow_download"] is True
    assert "attachment" in body["download_url"].replace("%20", " ").replace("%3B", ";")
    assert "inline" in body["preview_url"]
    # no owner, folder or workspace details in any field (the presigned URLs' storage key holds
    # only opaque ids)
    text = str({k: v for k, v in body.items() if not k.endswith("_url")})
    for private in ("owner", "workspace", "folder", "member@example.com"):
        assert private not in text


async def test_download_can_be_denied_and_only_safe_types_are_previewed(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, _, _ = await shared_document(client, db, storage)
    view_only = await create_link(client, users["member"], document["id"], allow_download=False)
    body = (await open_link(client, token_of(view_only.json()["url"]))).json()
    assert body["download_url"] is None and body["allow_download"] is False
    assert body["preview_url"] is not None

    archive = await upload_document(
        client,
        storage,
        users["member"],
        workspace_id=document["workspace_id"],
        filename="a.zip",
        mime_type="application/zip",
        data=b"PK\x03\x04" + b"\x00" * 20,
    )
    zipped = await create_link(client, users["member"], archive["id"], allow_download=False)
    body = (await open_link(client, token_of(zipped.json()["url"]))).json()
    assert body["download_url"] is None and body["preview_url"] is None  # nothing to show
    html = await upload_document(
        client,
        storage,
        users["member"],
        workspace_id=document["workspace_id"],
        filename="page.html",
        mime_type="text/html",
        data=b"<script>alert(1)</script>",
    )
    page = await create_link(client, users["member"], html["id"])
    body = (await open_link(client, token_of(page.json()["url"]))).json()
    assert body["preview_url"] is None  # never rendered inline
    assert "attachment" in body["download_url"].replace("%20", " ").replace("%3B", ";")


async def test_password_protected_links(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    _, _, _, token = await shared_document(client, db, storage, password="open-sesame")
    locked = await open_link(client, token)
    assert locked.status_code == 200 and locked.json()["requires_password"] is True
    assert locked.json()["filename"] is None and locked.json()["download_url"] is None

    wrong = await open_link(client, token, "not-it")
    assert wrong.status_code == 403 and wrong.json()["error"]["code"] == "BAD_PASSWORD"
    right = await open_link(client, token, "open-sesame")
    assert right.status_code == 200 and right.json()["filename"] == "report.pdf"


async def test_repeated_wrong_passwords_lock_that_client_out(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    _, _, _, token = await shared_document(client, db, storage, password="open-sesame")
    for _ in range(MAX_BAD_PASSWORDS):
        assert (await open_link(client, token, "guess")).status_code == 403
    locked = await open_link(client, token, "open-sesame")  # even the right one is refused now
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"


async def test_unknown_and_orphaned_links_all_look_like_no_link(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, _, token = await shared_document(client, db, storage)
    unknown = await open_link(client, "x" * 43)
    assert unknown.status_code == 404
    await client.delete(f"{API}/documents/{document['id']}", headers=users["member"].headers)
    assert (await open_link(client, token)).json() == unknown.json()  # deleted document
    await client.post(f"{API}/documents/{document['id']}/restore", headers=users["member"].headers)
    assert (await open_link(client, token)).status_code == 200  # back with the document
    await client.delete(
        f"{API}/workspaces/{document['workspace_id']}", headers=users["owner"].headers
    )
    assert (await open_link(client, token)).json() == unknown.json()  # deleted workspace


async def test_the_link_serves_the_current_version(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, _, token = await shared_document(client, db, storage)
    await upload_document(
        client,
        storage,
        users["member"],
        workspace_id=document["workspace_id"],
        document_id=document["id"],
        data=b"%PDF-1.7\nversion two\n",
    )
    body = (await open_link(client, token)).json()
    assert body["size_bytes"] == len(b"%PDF-1.7\nversion two\n")
    assert body["download_url"].split("?")[0].endswith("/2")


async def test_every_access_is_logged_and_visible_to_those_who_manage_the_link(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, users, link, token = await shared_document(
        client, db, storage, password="open-sesame"
    )
    await open_link(client, token)  # only asks for the password: not an access
    await open_link(client, token, "wrong", **{"user-agent": "TestBrowser/1.0"})
    await open_link(client, token, "open-sesame")
    await client.delete(f"{API}/share-links/{link['id']}", headers=users["member"].headers)
    await open_link(client, token)

    log = await client.get(
        f"{API}/share-links/{link['id']}/access-log", headers=users["member"].headers
    )
    assert log.status_code == 200
    body = log.json()
    assert body["total"] == 3
    assert [e["outcome"] for e in body["items"]] == ["revoked", "ok", "bad_password"]
    assert all(e["ip_address"] for e in body["items"])
    assert body["items"][2]["user_agent"] == "TestBrowser/1.0"

    assert (
        await client.get(
            f"{API}/share-links/{link['id']}/access-log", headers=users["outsider"].headers
        )
    ).status_code == 404
    rows = (await db.execute(select(ShareLinkAccessLog))).scalars().all()
    assert len(rows) == 3
    assert document["id"]


async def test_a_deleted_link_owner_document_row_is_not_needed_for_404(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    document, _, _, token = await shared_document(client, db, storage)
    await db.execute(
        update(Document)
        .where(Document.id == document["id"])
        .values(deleted_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db.commit()
    assert (await open_link(client, token)).status_code == 404
