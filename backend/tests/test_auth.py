"""Register, login and /auth/me."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_access_token
from app.models.user import User
from tests.helpers import API, PASSWORD, make_user


async def register(client: AsyncClient, **overrides: str):  # type: ignore[no-untyped-def]
    body = {"email": "ana@example.com", "password": PASSWORD, "name": "Ana Lee", **overrides}
    return await client.post(f"{API}/auth/register", json=body)


class TestRegister:
    async def test_creates_an_account_and_never_returns_the_password(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        response = await register(client)
        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"id", "email", "name", "email_verified"}
        assert body["email"] == "ana@example.com"
        assert len(body["id"]) == 12
        assert PASSWORD not in response.text

        stored = (await db.execute(select(User.password_hash))).scalar_one()
        assert stored.startswith("$argon2id$")
        assert PASSWORD not in stored

    async def test_email_is_stored_lower_case_and_name_is_trimmed(
        self, client: AsyncClient
    ) -> None:
        body = (await register(client, email="  Ana@Example.COM ", name="  Ana Lee  ")).json()
        assert body["email"] == "ana@example.com"
        assert body["name"] == "Ana Lee"

    async def test_duplicate_email_is_rejected_whatever_the_case(self, client: AsyncClient) -> None:
        assert (await register(client)).status_code == 201
        again = await register(client, email="ANA@example.com")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "EMAIL_TAKEN"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("email", "not-an-email"),
            ("email", ""),
            ("password", "short"),
            ("password", "x" * 129),
            ("name", "   "),
            ("name", "n" * 201),
        ],
    )
    async def test_invalid_input_is_a_422_in_the_standard_shape(
        self, client: AsyncClient, field: str, value: str
    ) -> None:
        response = await register(client, **{field: value})
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["message"].startswith(field)

    async def test_a_rejected_password_is_never_echoed_back(self, client: AsyncClient) -> None:
        response = await register(client, password="short")
        assert "short" not in response.json()["error"]["message"].replace("String should have", "")

    async def test_missing_fields_are_rejected(self, client: AsyncClient) -> None:
        response = await client.post(f"{API}/auth/register", json={"email": "a@b.co"})
        assert response.status_code == 422


class TestLogin:
    async def test_returns_a_token_and_the_user(self, client: AsyncClient) -> None:
        user = await make_user(client, "ana@example.com")
        assert user.token.count(".") == 2
        claims = decode_access_token(user.token)
        assert claims.user_id == user.id

    async def test_email_is_case_insensitive(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post(
            f"{API}/auth/login", json={"email": "ANA@Example.com", "password": PASSWORD}
        )
        assert response.status_code == 200

    async def test_wrong_password_and_unknown_email_look_identical(
        self, client: AsyncClient
    ) -> None:
        await register(client)
        wrong_password = await client.post(
            f"{API}/auth/login", json={"email": "ana@example.com", "password": "not the password"}
        )
        unknown_email = await client.post(
            f"{API}/auth/login",
            json={"email": "nobody@example.com", "password": "not the password"},
        )
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()
        assert wrong_password.json()["error"]["code"] == "BAD_CREDENTIALS"

    async def test_a_deactivated_account_cannot_log_in(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        await register(client)
        await db.execute(update(User).values(is_active=False))
        await db.commit()
        response = await client.post(
            f"{API}/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "BAD_CREDENTIALS"


class TestMe:
    async def test_returns_the_current_user(self, client: AsyncClient) -> None:
        user = await make_user(client, "ana@example.com", "Ana Lee")
        response = await client.get(f"{API}/auth/me", headers=user.headers)
        assert response.status_code == 200
        assert response.json() == {
            "id": user.id,
            "email": "ana@example.com",
            "name": "Ana Lee",
            "email_verified": True,
        }

    async def test_missing_token_is_401_with_a_bearer_challenge(self, client: AsyncClient) -> None:
        response = await client.get(f"{API}/auth/me")
        assert response.status_code == 401
        assert response.json() == {
            "error": {"code": "UNAUTHORIZED", "message": "Not authenticated."}
        }
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.parametrize("header", ["Bearer garbage", "Bearer ", "Basic YTpi", "garbage"])
    async def test_malformed_credentials_are_401(self, client: AsyncClient, header: str) -> None:
        response = await client.get(f"{API}/auth/me", headers={"Authorization": header})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"

    async def test_expired_token_is_401(self, client: AsyncClient) -> None:
        user = await make_user(client, "ana@example.com")
        expired, _ = create_access_token(user.id, now=datetime.now(UTC) - timedelta(days=3))
        response = await client.get(
            f"{API}/auth/me", headers={"Authorization": f"Bearer {expired}"}
        )
        assert response.status_code == 401

    async def test_token_for_a_user_that_does_not_exist_is_401(self, client: AsyncClient) -> None:
        token, _ = create_access_token("NoSuchUser01")
        response = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_a_deactivated_user_loses_access_immediately(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        user = await make_user(client, "ana@example.com")
        await db.execute(update(User).values(is_active=False))
        await db.commit()
        response = await client.get(f"{API}/auth/me", headers=user.headers)
        assert response.status_code == 401


class TestErrorShape:
    async def test_unknown_route_uses_the_standard_error_shape(self, client: AsyncClient) -> None:
        response = await client.get(f"{API}/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    async def test_wrong_method_uses_the_standard_error_shape(self, client: AsyncClient) -> None:
        response = await client.get(f"{API}/auth/login")
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
