"""Invitations (FR-18, FR-21): who can invite, delivery, acceptance and its safeguards."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog
from app.models.enums import WorkspaceRole
from app.models.workspace import Workspace, WorkspaceInvite, WorkspaceMember
from tests.fake_mailer import FakeMailer
from tests.fake_storage import FakeStorage
from tests.helpers import (
    API,
    TestUser,
    make_user,
    make_workspace,
    upload_document,
    workspace_with_roles,
)


async def invite(
    client: AsyncClient,
    actor: TestUser,
    workspace_id: str,
    email: str,
    role: str = "member",
    **extra: Any,
) -> Response:
    return await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        json={"email": email, "role": role, **extra},
        headers=actor.headers,
    )


def token_of(url: str) -> str:
    return url.rsplit("/invites/", 1)[1]


async def accept(client: AsyncClient, user: TestUser | None, token: str) -> Response:
    headers = user.headers if user else {}
    return await client.post(f"{API}/invites/{token}/accept", headers=headers)


# ---- creating, listing, revoking -------------------------------------------------------------


async def test_admin_invites_by_email_and_gets_the_link_once(
    client: AsyncClient, db: AsyncSession, mailer: FakeMailer
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    response = await invite(client, users["admin"], workspace["id"], "new.person@example.com")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new.person@example.com" and body["role"] == "member"
    assert body["email_sent"] is True and body["expired"] is False
    assert "/invites/" in body["url"]

    assert len(mailer.sent) == 1
    message = mailer.sent[0]
    assert message.to == "new.person@example.com"
    assert workspace["name"] in message.subject and users["admin"].name in message.subject
    assert mailer.last_link("/invites/") == body["url"]

    listed = await client.get(
        f"{API}/workspaces/{workspace['id']}/invites", headers=users["owner"].headers
    )
    assert [i["email"] for i in listed.json()] == ["new.person@example.com"]
    assert listed.json()[0].get("url") is None  # the link is never shown again


async def test_the_token_is_stored_only_as_a_hash(
    client: AsyncClient, db: AsyncSession, mailer: FakeMailer
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    body = (await invite(client, users["owner"], workspace["id"], "x@example.com")).json()
    token = token_of(body["url"])
    row = (await db.execute(select(WorkspaceInvite))).scalar_one()
    assert row.token_hash != token and len(token) >= 43
    assert token not in row.token_hash


async def test_only_admins_and_owners_can_invite_and_see_invites(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    for role in ("member", "guest"):
        assert (await invite(client, users[role], ws, "a@example.com")).status_code == 403
        listed = await client.get(f"{API}/workspaces/{ws}/invites", headers=users[role].headers)
        assert listed.status_code == 403
    assert (await invite(client, users["outsider"], ws, "a@example.com")).status_code == 404
    assert (
        await client.get(f"{API}/workspaces/{ws}/invites", headers=users["outsider"].headers)
    ).status_code == 404
    assert (await client.post(f"{API}/workspaces/{ws}/invites", json={})).status_code == 401


async def test_validation(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    assert (await invite(client, users["owner"], ws, "a@example.com", "owner")).status_code == 422
    assert (await invite(client, users["owner"], ws, "not-an-email")).status_code == 422
    missing_document = await invite(
        client, users["owner"], ws, "g@example.com", "guest", document_ids=["nope"]
    )
    assert missing_document.status_code == 404


async def test_duplicates_are_refused_and_expired_invites_are_replaced(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws, owner = workspace["id"], users["owner"]
    member = await invite(client, owner, ws, users["member"].email)
    assert member.status_code == 409 and member.json()["error"]["code"] == "ALREADY_MEMBER"
    first = await invite(client, owner, ws, "dup@example.com")
    assert first.status_code == 201
    again = await invite(client, owner, ws, "DUP@example.com")
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVITE_PENDING"

    await db.execute(
        update(WorkspaceInvite).values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db.commit()
    assert (await invite(client, owner, ws, "dup@example.com")).status_code == 201


async def test_revoke_then_reinvite(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    created = (await invite(client, users["admin"], ws, "r@example.com")).json()
    url = f"{API}/workspaces/{ws}/invites/{created['id']}"
    assert (await client.delete(url, headers=users["member"].headers)).status_code == 403
    assert (await client.delete(url, headers=users["outsider"].headers)).status_code == 404
    assert (await client.delete(url, headers=users["admin"].headers)).status_code == 204
    assert (await client.delete(url, headers=users["admin"].headers)).status_code == 404
    listed = await client.get(f"{API}/workspaces/{ws}/invites", headers=users["admin"].headers)
    assert listed.json() == []
    assert (await invite(client, users["admin"], ws, "r@example.com")).status_code == 201


async def test_invites_of_another_workspace_are_out_of_reach(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    other_owner = await make_user(client, "other@example.com")
    other = await make_workspace(client, other_owner, "Other")
    created = (await invite(client, users["owner"], workspace["id"], "z@example.com")).json()
    # an admin of ANOTHER workspace can neither list nor revoke it, even naming the invite id
    cross = await client.delete(
        f"{API}/workspaces/{other['id']}/invites/{created['id']}", headers=other_owner.headers
    )
    assert cross.status_code == 404
    listed = await client.get(
        f"{API}/workspaces/{other['id']}/invites", headers=other_owner.headers
    )
    assert listed.json() == []


async def test_a_failed_email_does_not_fail_the_invite(
    client: AsyncClient, db: AsyncSession, mailer: FakeMailer
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    mailer.fail = True
    response = await invite(client, users["owner"], workspace["id"], "n@example.com")
    assert response.status_code == 201
    body = response.json()
    assert body["email_sent"] is False and body["url"]  # the admin can hand the link over


async def test_invitations_are_logged(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    created = (await invite(client, users["owner"], ws, "l@example.com")).json()
    await client.delete(
        f"{API}/workspaces/{ws}/invites/{created['id']}", headers=users["owner"].headers
    )
    actions = (
        await db.execute(select(ActivityLog.action).order_by(ActivityLog.created_at))
    ).scalars()
    assert list(actions) == ["workspace.created", "member.invited", "invite.revoked"]


# ---- preview and accept ----------------------------------------------------------------------


async def test_preview_needs_no_account_and_shows_only_what_the_invite_is_for(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    body = (await invite(client, users["owner"], workspace["id"], "p@example.com", "admin")).json()
    response = await client.get(f"{API}/invites/{token_of(body['url'])}")
    assert response.status_code == 200
    assert response.json() == {
        "workspace_name": workspace["name"],
        "role": "admin",
        "email": "p@example.com",
        "expired": False,
    }
    assert (await client.get(f"{API}/invites/{'x' * 43}")).status_code == 404


async def test_the_invited_person_signs_up_then_accepts(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    body = (
        await invite(client, users["admin"], workspace["id"], "newbie@example.com", "member")
    ).json()
    newbie = await make_user(client, "newbie@example.com")  # signs up first, as the email says
    assert (await accept(client, None, token_of(body["url"]))).status_code == 401

    assert (await accept(client, newbie, token_of(body["url"]))).status_code == 204
    mine = await client.get(f"{API}/workspaces", headers=newbie.headers)
    assert [(w["id"], w["role"]) for w in mine.json()] == [(workspace["id"], "member")]
    row = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace["id"],
                WorkspaceMember.user_id == newbie.id,
            )
        )
    ).scalar_one()
    assert row.role == WorkspaceRole.MEMBER and row.invited_by == users["admin"].id
    actions = (await db.execute(select(ActivityLog.action))).scalars()
    assert "member.joined" in list(actions)
    listed = await client.get(
        f"{API}/workspaces/{workspace['id']}/invites", headers=users["admin"].headers
    )
    assert listed.json() == []  # no longer pending

    assert (await accept(client, newbie, token_of(body["url"]))).status_code == 204  # idempotent
    preview = await client.get(f"{API}/invites/{token_of(body['url'])}")
    assert preview.status_code == 410 and preview.json()["error"]["code"] == "INVITE_USED"


async def test_a_guest_invite_grants_its_documents_on_acceptance(
    client: AsyncClient, db: AsyncSession, storage: FakeStorage
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    shared = await upload_document(
        client, storage, users["member"], workspace_id=ws, filename="a.pdf"
    )
    await upload_document(client, storage, users["member"], workspace_id=ws, filename="b.pdf")
    body = (
        await invite(
            client, users["admin"], ws, "guest2@example.com", "guest", document_ids=[shared["id"]]
        )
    ).json()
    guest = await make_user(client, "guest2@example.com")
    await accept(client, guest, token_of(body["url"]))
    listed = await client.get(
        f"{API}/documents", params={"workspace_id": ws}, headers=guest.headers
    )
    assert [d["id"] for d in listed.json()["items"]] == [shared["id"]]
    members = await client.get(f"{API}/workspaces/{ws}/members", headers=users["admin"].headers)
    granted = {m["user_id"]: m["granted_document_ids"] for m in members.json()}
    assert granted[guest.id] == [shared["id"]]


async def test_only_the_invited_email_can_accept(client: AsyncClient, db: AsyncSession) -> None:
    workspace, users = await workspace_with_roles(client, db)
    body = (await invite(client, users["owner"], workspace["id"], "right@example.com")).json()
    wrong = await make_user(client, "wrong@example.com")
    response = await accept(client, wrong, token_of(body["url"]))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVITE_EMAIL_MISMATCH"
    mine = await client.get(f"{API}/workspaces", headers=wrong.headers)
    assert mine.json() == []
    # the email match is case-insensitive
    right = await make_user(client, "Right@Example.com")
    assert (await accept(client, right, token_of(body["url"]))).status_code == 204


async def test_expired_revoked_and_orphaned_invitations_cannot_be_accepted(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    person = await make_user(client, "late@example.com")

    expired = (await invite(client, users["owner"], ws, "late@example.com")).json()
    await db.execute(
        update(WorkspaceInvite).values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db.commit()
    response = await accept(client, person, token_of(expired["url"]))
    assert response.status_code == 410 and response.json()["error"]["code"] == "INVITE_EXPIRED"
    assert (await client.get(f"{API}/invites/{token_of(expired['url'])}")).status_code == 410

    fresh = (await invite(client, users["owner"], ws, "late@example.com")).json()
    await client.delete(
        f"{API}/workspaces/{ws}/invites/{fresh['id']}", headers=users["owner"].headers
    )
    response = await accept(client, person, token_of(fresh["url"]))
    assert response.status_code == 410 and response.json()["error"]["code"] == "INVITE_REVOKED"

    last = (await invite(client, users["owner"], ws, "late@example.com")).json()
    await db.execute(
        update(Workspace).where(Workspace.id == ws).values(deleted_at=datetime.now(UTC))
    )
    await db.commit()
    assert (await accept(client, person, token_of(last["url"]))).status_code == 404


async def test_a_removed_member_cannot_reuse_an_accepted_invitation(
    client: AsyncClient, db: AsyncSession
) -> None:
    workspace, users = await workspace_with_roles(client, db)
    ws = workspace["id"]
    body = (await invite(client, users["owner"], ws, "once@example.com")).json()
    person = await make_user(client, "once@example.com")
    await accept(client, person, token_of(body["url"]))
    removed = await client.delete(
        f"{API}/workspaces/{ws}/members/{person.id}", headers=users["owner"].headers
    )
    assert removed.status_code == 204
    again = await accept(client, person, token_of(body["url"]))
    assert again.status_code == 410 and again.json()["error"]["code"] == "INVITE_USED"
