"""Password hashing and JWT handling (app/core/security.py). No database needed."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswords:
    def test_hash_verifies_and_is_argon2id(self) -> None:
        hashed = hash_password("correct horse battery")
        assert hashed.startswith("$argon2id$")
        assert verify_password("correct horse battery", hashed)
        assert not verify_password("wrong password", hashed)

    def test_same_password_hashes_differently(self) -> None:
        assert hash_password("same password") != hash_password("same password")

    def test_password_is_not_in_the_hash(self) -> None:
        assert "hunter2hunter2" not in hash_password("hunter2hunter2")

    def test_unknown_user_never_verifies(self) -> None:
        # no stored hash: still does the work, and always fails
        assert verify_password("anything", None) is False


class TestAccessTokens:
    def test_round_trip(self) -> None:
        token, claims = create_access_token("user123")
        decoded = decode_access_token(token)
        assert decoded.user_id == "user123"
        assert decoded.jti == claims.jti
        assert decoded.expires_at == claims.expires_at

    def test_lifetime_follows_settings(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        _, claims = create_access_token("u", now=now)
        expected = now + timedelta(minutes=get_settings().jwt_expire_minutes)
        assert claims.expires_at == expected

    def test_every_token_has_its_own_jti(self) -> None:
        jtis = {create_access_token("u")[1].jti for _ in range(50)}
        assert len(jtis) == 50

    def test_jti_is_at_least_128_bits(self) -> None:
        assert len(create_access_token("u")[1].jti) >= 22  # 16 random bytes, url-safe base64

    def test_expired_token_is_rejected(self) -> None:
        token, _ = create_access_token("u", now=datetime.now(UTC) - timedelta(days=3))
        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    def test_tampered_token_is_rejected(self) -> None:
        token, _ = create_access_token("u")
        header, payload, signature = token.split(".")
        forged = ".".join(
            [header, payload, signature[:-2] + ("AA" if signature[-2:] != "AA" else "BB")]
        )
        with pytest.raises(InvalidTokenError):
            decode_access_token(forged)

    def test_token_signed_with_another_secret_is_rejected(self) -> None:
        now = datetime.now(UTC)
        payload = {"sub": "u", "jti": "j" * 22, "iat": now, "exp": now + timedelta(hours=1)}
        token = jwt.encode(payload, "a-completely-different-secret-value-123456", algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    def test_alg_none_is_rejected(self) -> None:
        now = datetime.now(UTC)
        payload = {"sub": "u", "jti": "j" * 22, "iat": now, "exp": now + timedelta(hours=1)}
        unsigned = jwt.encode(payload, key="", algorithm="none")
        with pytest.raises(InvalidTokenError):
            decode_access_token(unsigned)

    @pytest.mark.parametrize("missing", ["sub", "jti", "exp", "iat"])
    def test_token_missing_a_required_claim_is_rejected(self, missing: str) -> None:
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "sub": "u",
            "jti": "j" * 22,
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        del payload[missing]
        token = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    @pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x", "\x00"])
    def test_garbage_is_rejected(self, garbage: str) -> None:
        with pytest.raises(InvalidTokenError):
            decode_access_token(garbage)
