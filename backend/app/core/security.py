"""Password hashing and JWT helpers. All password and token handling lives in this module."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.config import get_settings

_ALGORITHM = "HS256"
_passwords = CryptContext(schemes=["argon2"], deprecated="auto")

# Verified against when the email is unknown, so a login attempt takes about as long whether or
# not the account exists (otherwise response time would reveal which emails are registered).
_DUMMY_HASH = _passwords.hash("password-used-only-to-equalise-timing")


def hash_password(password: str) -> str:
    return _passwords.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _passwords.verify(password, _DUMMY_HASH)
        return False
    return bool(_passwords.verify(password, password_hash))


class InvalidTokenError(Exception):
    """The token is malformed, forged, expired, or missing a required claim."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    jti: str  # unique per token; what logout stores to revoke it
    expires_at: datetime


def create_access_token(user_id: str, *, now: datetime | None = None) -> tuple[str, TokenClaims]:
    settings = get_settings()
    issued_at = (now or datetime.now(UTC)).replace(microsecond=0)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expire_minutes)
    jti = secrets.token_urlsafe(16)  # 128 bits
    payload = {"sub": user_id, "jti": jti, "iat": issued_at, "exp": expires_at}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)
    return token, TokenClaims(user_id=user_id, jti=jti, expires_at=expires_at)


def decode_access_token(token: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[_ALGORITHM],  # pinned: rejects "alg": "none" and algorithm confusion
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc
    user_id, jti = payload.get("sub"), payload.get("jti")
    if not isinstance(user_id, str) or not user_id or not isinstance(jti, str) or not jti:
        raise InvalidTokenError
    return TokenClaims(
        user_id=user_id, jti=jti, expires_at=datetime.fromtimestamp(payload["exp"], UTC)
    )
