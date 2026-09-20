from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import TokenClaims, hash_password, verify_password
from app.models.revoked_token import RevokedToken
from app.models.user import User


def _email_taken() -> ApiError:
    return ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.")


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    return result.scalar_one_or_none()


async def register_user(session: AsyncSession, *, email: str, password: str, name: str) -> User:
    if await get_user_by_email(session, email) is not None:
        raise _email_taken()
    user = User(email=email, password_hash=hash_password(password), name=name)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        # two registrations for the same email raced past the check above
        await session.rollback()
        if "uq_users_email_lower" in str(exc.orig):
            raise _email_taken() from exc
        raise
    return user


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    """Return the user, or raise the one BAD_CREDENTIALS error for every kind of failure."""
    user = await get_user_by_email(session, email)
    # always verify (against a dummy hash if there is no such user) so timing is the same
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        raise ApiError(401, "BAD_CREDENTIALS", "Wrong email or password.")
    return user


async def is_token_revoked(session: AsyncSession, jti: str) -> bool:
    result = await session.execute(select(RevokedToken.id).where(RevokedToken.jti == jti))
    return result.first() is not None


async def purge_expired_revoked_tokens(session: AsyncSession) -> int:
    """Delete blacklist rows whose token has expired anyway. Returns how many were removed.
    Does not commit."""
    result = await session.execute(delete(RevokedToken).where(RevokedToken.expires_at < func.now()))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def revoke_token(session: AsyncSession, claims: TokenClaims) -> None:
    """Blacklist a token (logout). Safe to call twice: a duplicate is not an error."""
    await purge_expired_revoked_tokens(session)  # keeps the table small
    await session.execute(
        pg_insert(RevokedToken)
        .values(jti=claims.jti, user_id=claims.user_id, expires_at=claims.expires_at)
        .on_conflict_do_nothing(index_elements=["jti"])
    )
    await session.commit()
