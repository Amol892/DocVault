"""Email verification (FR-1) and password reset (FR-4)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.auth_token import AuthToken
from app.models.user import User
from tests.fake_mailer import FakeMailer
from tests.helpers import API, PASSWORD, TestUser

NEW_PASSWORD = "a-brand-new-password"


@pytest.fixture
def verification_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "require_email_verification", True)


async def register(client: AsyncClient, email: str = "new@example.com") -> Response:
    return await client.post(
        f"{API}/auth/register", json={"email": email, "password": PASSWORD, "name": "New Person"}
    )


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> Response:
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


async def signed_in(
    client: AsyncClient, email: str = "new@example.com", password: str = PASSWORD
) -> TestUser:
    body = (await login(client, email, password)).json()
    return TestUser(id=body["user"]["id"], email=email, name="New Person", token=body["token"])


def token_from(link: str) -> str:
    return link.rsplit("/", 1)[1]


async def verify(client: AsyncClient, token: str) -> Response:
    return await client.post(f"{API}/auth/verify-email", json={"token": token})


# ---- verification ----------------------------------------------------------------------------


async def test_a_new_account_is_unverified_and_gets_an_email(
    client: AsyncClient, mailer: FakeMailer, verification_on: None
) -> None:
    response = await register(client)
    assert response.status_code == 201 and response.json()["email_verified"] is False
    assert len(mailer.sent) == 1 and mailer.sent[0].to == "new@example.com"
    assert "/verify-email/" in mailer.last_link("/verify-email/")


async def test_verification_can_be_switched_off(client: AsyncClient, mailer: FakeMailer) -> None:
    response = await register(client)  # the test default: REQUIRE_EMAIL_VERIFICATION=false
    assert response.json()["email_verified"] is True and mailer.sent == []


async def test_an_unverified_user_can_sign_in_but_reaches_nothing_else(
    client: AsyncClient, verification_on: None
) -> None:
    await register(client)
    user = await signed_in(client)
    me = await client.get(f"{API}/auth/me", headers=user.headers)
    assert me.status_code == 200 and me.json()["email_verified"] is False

    for method, path in [
        ("GET", "/workspaces"),
        ("POST", "/workspaces"),
        ("GET", "/documents"),
        ("POST", "/documents/upload-url"),
        ("POST", "/invites/sometoken/accept"),
    ]:
        response = await client.request(method, f"{API}{path}", json={}, headers=user.headers)
        assert response.status_code == 403, (method, path)
        assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED", (method, path)
    assert (await client.post(f"{API}/auth/logout", headers=user.headers)).status_code == 204


async def test_opening_the_link_verifies_the_account_exactly_once(
    client: AsyncClient, db: AsyncSession, mailer: FakeMailer, verification_on: None
) -> None:
    await register(client)
    user = await signed_in(client)
    token = token_from(mailer.last_link("/verify-email/"))
    row = (await db.execute(select(AuthToken))).scalar_one()
    assert row.token_hash != token  # only the hash is stored

    assert (await verify(client, token)).status_code == 204  # no account session needed
    me = await client.get(f"{API}/auth/me", headers=user.headers)
    assert me.json()["email_verified"] is True
    assert (await client.get(f"{API}/workspaces", headers=user.headers)).status_code == 200

    again = await verify(client, token)
    assert again.status_code == 400 and again.json()["error"]["code"] == "INVALID_TOKEN"


async def test_bad_expired_and_wrong_purpose_tokens_look_the_same(
    client: AsyncClient, db: AsyncSession, mailer: FakeMailer, verification_on: None
) -> None:
    await register(client, "a@example.com")
    unknown = await verify(client, "x" * 43)
    assert unknown.status_code == 400

    token = token_from(mailer.last_link("/verify-email/"))
    await db.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await db.commit()
    expired = await verify(client, token)
    assert expired.status_code == 400 and expired.json() == unknown.json()

    # a verification token is no use for resetting a password
    await register(client, "b@example.com")
    other = token_from(mailer.last_link("/verify-email/"))
    swapped = await client.post(
        f"{API}/auth/reset-password", json={"token": other, "password": NEW_PASSWORD}
    )
    assert swapped.status_code == 400 and swapped.json() == unknown.json()


async def test_resend_replaces_the_link_and_is_rate_limited(
    client: AsyncClient,
    mailer: FakeMailer,
    verification_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "token_cooldown_seconds", 60)
    await register(client)
    user = await signed_in(client)
    first = token_from(mailer.last_link("/verify-email/"))

    too_soon = await client.post(f"{API}/auth/resend-verification", headers=user.headers)
    assert too_soon.status_code == 429 and len(mailer.sent) == 1

    monkeypatch.setattr(get_settings(), "token_cooldown_seconds", 0)
    assert (
        await client.post(f"{API}/auth/resend-verification", headers=user.headers)
    ).status_code == 204
    second = token_from(mailer.last_link("/verify-email/"))
    assert second != first and len(mailer.sent) == 2
    assert (await verify(client, first)).status_code == 400  # the old link is dead
    assert (await verify(client, second)).status_code == 204

    # already verified: nothing to do, nothing sent
    assert (
        await client.post(f"{API}/auth/resend-verification", headers=user.headers)
    ).status_code == 204
    assert len(mailer.sent) == 2
    assert (await client.post(f"{API}/auth/resend-verification")).status_code == 401


async def test_accounts_that_existed_before_verification_stay_verified(
    client: AsyncClient, db: AsyncSession
) -> None:
    db.add(User(email="old@example.com", password_hash="x", name="Old"))  # no flag set
    await db.commit()
    user = (await db.execute(select(User).where(User.email == "old@example.com"))).scalar_one()
    assert user.email_verified is True  # the column's server default


# ---- password reset --------------------------------------------------------------------------


async def forgot(client: AsyncClient, email: str) -> Response:
    return await client.post(f"{API}/auth/forgot-password", json={"email": email})


async def test_forgot_password_emails_a_link_and_reveals_nothing(
    client: AsyncClient, mailer: FakeMailer
) -> None:
    await register(client, "known@example.com")
    mailer.sent.clear()
    known = await forgot(client, "known@example.com")
    unknown = await forgot(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 204
    assert known.content == unknown.content
    assert [m.to for m in mailer.sent] == ["known@example.com"]  # only the real account
    assert "/reset-password/" in mailer.sent[0].body
    assert (
        await client.post(f"{API}/auth/forgot-password", json={"email": "bad"})
    ).status_code == 422


async def test_reset_sets_the_new_password_once(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession
) -> None:
    await register(client, "known@example.com")
    await forgot(client, "known@example.com")
    token = token_from(mailer.last_link("/reset-password/"))

    reset = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )
    assert reset.status_code == 204
    assert (await login(client, "known@example.com", PASSWORD)).status_code == 401
    assert (await login(client, "known@example.com", NEW_PASSWORD)).status_code == 200

    again = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "password": "another-password-1"}
    )
    assert again.status_code == 400 and again.json()["error"]["code"] == "INVALID_TOKEN"
    assert (await login(client, "known@example.com", NEW_PASSWORD)).status_code == 200
    row = (await db.execute(select(AuthToken))).scalar_one()
    assert row.used_at is not None and row.token_hash != token


async def test_reset_validation_and_expiry(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession
) -> None:
    await register(client, "known@example.com")
    await forgot(client, "known@example.com")
    token = token_from(mailer.last_link("/reset-password/"))
    short = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "password": "short"}
    )
    assert short.status_code == 422
    # a rejected password does not burn the link
    await db.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()
    expired = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )
    assert expired.status_code == 400
    assert (await login(client, "known@example.com", PASSWORD)).status_code == 200


async def test_a_new_request_kills_the_earlier_link(
    client: AsyncClient, mailer: FakeMailer
) -> None:
    await register(client, "known@example.com")
    await forgot(client, "known@example.com")
    old = token_from(mailer.last_link("/reset-password/"))
    await forgot(client, "known@example.com")
    new = token_from(mailer.last_link("/reset-password/"))
    assert old != new
    stale = await client.post(
        f"{API}/auth/reset-password", json={"token": old, "password": NEW_PASSWORD}
    )
    assert stale.status_code == 400
    fresh = await client.post(
        f"{API}/auth/reset-password", json={"token": new, "password": NEW_PASSWORD}
    )
    assert fresh.status_code == 204


async def test_reset_requests_are_throttled_per_account(
    client: AsyncClient, mailer: FakeMailer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "token_cooldown_seconds", 60)
    await register(client, "known@example.com")
    for _ in range(3):
        assert (
            await forgot(client, "known@example.com")
        ).status_code == 204  # same answer every time
    assert len(mailer.sent) == 1  # but only one email went out


async def test_resetting_also_verifies_an_unverified_account(
    client: AsyncClient, mailer: FakeMailer, verification_on: None
) -> None:
    await register(client, "known@example.com")
    await forgot(client, "known@example.com")
    token = token_from(mailer.last_link("/reset-password/"))
    await client.post(f"{API}/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})
    user = await signed_in(client, "known@example.com", NEW_PASSWORD)
    assert (await client.get(f"{API}/auth/me", headers=user.headers)).json()[
        "email_verified"
    ] is True


async def test_deactivated_accounts_get_no_reset_email(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession
) -> None:
    await register(client, "gone@example.com")
    await db.execute(update(User).values(is_active=False))
    await db.commit()
    assert (await forgot(client, "gone@example.com")).status_code == 204
    assert mailer.sent == []
