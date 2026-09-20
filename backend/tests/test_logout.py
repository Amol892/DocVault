"""Logout and server-side token revocation (the revoked_tokens blacklist)."""

import asyncio
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.models.revoked_token import RevokedToken
from app.services import accounts
from tests.helpers import API, PASSWORD, make_user, make_workspace


async def revoked_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(RevokedToken))).scalar_one()


async def login_again(client: AsyncClient, email: str) -> str:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    token: str = response.json()["token"]
    return token


class TestLogout:
    async def test_logout_returns_204_and_the_token_stops_working(
        self, client: AsyncClient
    ) -> None:
        user = await make_user(client, "ana@example.com")
        assert (await client.get(f"{API}/auth/me", headers=user.headers)).status_code == 200

        response = await client.post(f"{API}/auth/logout", headers=user.headers)
        assert response.status_code == 204
        assert response.content == b""

        after = await client.get(f"{API}/auth/me", headers=user.headers)
        assert after.status_code == 401
        assert after.json()["error"]["code"] == "UNAUTHORIZED"

    async def test_a_revoked_token_is_rejected_by_every_endpoint(self, client: AsyncClient) -> None:
        user = await make_user(client, "ana@example.com")
        workspace = await make_workspace(client, user)
        await client.post(f"{API}/auth/logout", headers=user.headers)

        for method, path in [
            ("GET", "/workspaces"),
            ("POST", "/workspaces"),
            ("GET", f"/workspaces/{workspace['id']}"),
            ("GET", f"/workspaces/{workspace['id']}/members"),
            ("POST", "/auth/logout"),
        ]:
            response = await client.request(method, f"{API}{path}", headers=user.headers, json={})
            assert response.status_code == 401, f"{method} {path}"

    async def test_logging_out_twice_with_the_same_token_is_401(self, client: AsyncClient) -> None:
        user = await make_user(client, "ana@example.com")
        assert (await client.post(f"{API}/auth/logout", headers=user.headers)).status_code == 204
        assert (await client.post(f"{API}/auth/logout", headers=user.headers)).status_code == 401

    async def test_logout_needs_a_token(self, client: AsyncClient) -> None:
        assert (await client.post(f"{API}/auth/logout")).status_code == 401

    async def test_other_sessions_of_the_same_user_stay_valid(self, client: AsyncClient) -> None:
        user = await make_user(client, "ana@example.com")
        second_token = await login_again(client, "ana@example.com")
        assert second_token != user.token

        await client.post(f"{API}/auth/logout", headers=user.headers)

        still_ok = await client.get(
            f"{API}/auth/me", headers={"Authorization": f"Bearer {second_token}"}
        )
        assert still_ok.status_code == 200

    async def test_logging_out_does_not_affect_other_users(self, client: AsyncClient) -> None:
        ana = await make_user(client, "ana@example.com")
        bob = await make_user(client, "bob@example.com")
        await client.post(f"{API}/auth/logout", headers=ana.headers)
        assert (await client.get(f"{API}/auth/me", headers=bob.headers)).status_code == 200

    async def test_can_log_in_again_after_logging_out(self, client: AsyncClient) -> None:
        user = await make_user(client, "ana@example.com")
        await client.post(f"{API}/auth/logout", headers=user.headers)
        fresh = await login_again(client, "ana@example.com")
        response = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {fresh}"})
        assert response.status_code == 200


class TestBlacklistStorage:
    async def test_the_row_records_the_token_id_owner_and_expiry(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        user = await make_user(client, "ana@example.com")
        claims = decode_access_token(user.token)
        await client.post(f"{API}/auth/logout", headers=user.headers)

        row = (await db.execute(select(RevokedToken))).scalar_one()
        assert row.jti == claims.jti
        assert row.user_id == user.id
        assert row.expires_at == claims.expires_at
        assert row.created_at is not None  # the moment of revocation

    async def test_the_token_itself_is_not_stored(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        user = await make_user(client, "ana@example.com")
        await client.post(f"{API}/auth/logout", headers=user.headers)
        row = (await db.execute(select(RevokedToken))).scalar_one()
        assert user.token not in {row.jti, row.user_id, row.id}

    async def test_revoking_the_same_token_twice_is_not_an_error(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        user = await make_user(client, "ana@example.com")
        claims = decode_access_token(user.token)
        await accounts.revoke_token(db, claims)
        await accounts.revoke_token(db, claims)  # e.g. two logouts racing each other
        assert await revoked_count(db) == 1

    async def test_concurrent_logouts_with_one_token_never_error(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        user = await make_user(client, "ana@example.com")
        responses = await asyncio.gather(
            *[client.post(f"{API}/auth/logout", headers=user.headers) for _ in range(4)]
        )
        assert all(r.status_code in (204, 401) for r in responses)
        assert any(r.status_code == 204 for r in responses)
        assert await revoked_count(db) == 1

    async def test_expired_rows_are_purged_and_live_ones_kept(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        user = await make_user(client, "ana@example.com")
        now = datetime.now(UTC)
        db.add_all(
            [
                RevokedToken(
                    jti="expired-one", user_id=user.id, expires_at=now - timedelta(hours=1)
                ),
                RevokedToken(
                    jti="expired-two", user_id=user.id, expires_at=now - timedelta(days=2)
                ),
                RevokedToken(
                    jti="still-live", user_id=user.id, expires_at=now + timedelta(hours=5)
                ),
            ]
        )
        await db.commit()

        removed = await accounts.purge_expired_revoked_tokens(db)
        await db.commit()

        assert removed == 2
        remaining = (await db.execute(select(RevokedToken.jti))).scalars().all()
        assert remaining == ["still-live"]

    async def test_logout_cleans_up_expired_rows(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        user = await make_user(client, "ana@example.com")
        db.add(
            RevokedToken(
                jti="long-expired",
                user_id=user.id,
                expires_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        await db.commit()

        await client.post(f"{API}/auth/logout", headers=user.headers)

        jtis = (await db.execute(select(RevokedToken.jti))).scalars().all()
        assert "long-expired" not in jtis
        assert decode_access_token(user.token).jti in jtis
