"""Email verification (FR-1) and password reset (FR-4).

Both use single-use, expiring tokens sent by email. Only the SHA-256 hash is stored, and a token
is consumed with one conditional UPDATE, so two requests can never both use it. Nothing here
reveals whether an email address has an account.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ApiError
from app.core.security import hash_password
from app.models.auth_token import AuthToken
from app.models.enums import AuthTokenPurpose
from app.models.user import User
from app.services.accounts import get_user_by_email
from app.services.email_templates import render
from app.services.mailer import EmailMessage, Mailer, send_quietly

TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _invalid() -> ApiError:
    # unknown, expired and already-used tokens are indistinguishable on purpose
    return ApiError(400, "INVALID_TOKEN", "This link is invalid or has expired.")


async def _issue(
    session: AsyncSession, user: User, purpose: AuthTokenPurpose, lifetime: timedelta
) -> str:
    """A fresh token; any earlier unused one for the same purpose stops working. Commits."""
    now = datetime.now(UTC)
    await session.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None)
        )
        .values(used_at=now)
    )
    token = secrets.token_urlsafe(TOKEN_BYTES)
    session.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=now + lifetime,
        )
    )
    await session.commit()
    return token


async def _consume(session: AsyncSession, token: str, purpose: AuthTokenPurpose) -> str:
    """Use a token exactly once; returns the user id. One statement, so it is race-free."""
    row = (
        await session.execute(
            update(AuthToken)
            .where(
                AuthToken.token_hash == hash_token(token),
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > func.now(),
            )
            .values(used_at=func.now())
            .returning(AuthToken.user_id)
        )
    ).first()
    if row is None:
        await session.rollback()
        raise _invalid()
    return str(row[0])


async def _issued_recently(session: AsyncSession, user: User, purpose: AuthTokenPurpose) -> bool:
    since = datetime.now(UTC) - timedelta(seconds=get_settings().token_cooldown_seconds)
    found = await session.execute(
        select(AuthToken.id).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.created_at > since,
        )
    )
    return found.first() is not None


def _link(path: str, token: str) -> str:
    return f"{get_settings().frontend_url.rstrip('/')}{path}/{token}"


# ---- email verification ----------------------------------------------------------------------


async def send_verification(session: AsyncSession, mailer: Mailer, user: User) -> bool:
    token = await _issue(
        session,
        user,
        AuthTokenPurpose.VERIFY_EMAIL,
        timedelta(hours=get_settings().verify_token_expire_hours),
    )
    url = _link("/verify-email", token)
    hours = get_settings().verify_token_expire_hours
    return await send_quietly(
        mailer,
        EmailMessage(
            to=user.email,
            subject="Confirm your email address for DocVault",
            body=(
                f"Hi {user.name},\n\nConfirm your email address to finish setting up your "
                f"account:\n{url}\n\n"
                f"The link works once and expires in {hours} hours. If you didn't create a "
                "DocVault account, ignore this email."
            ),
            html=render("verify_email.html", name=user.name, url=url, expire_hours=hours),
        ),
    )


async def resend_verification(session: AsyncSession, mailer: Mailer, user: User) -> None:
    if user.email_verified:
        return
    if await _issued_recently(session, user, AuthTokenPurpose.VERIFY_EMAIL):
        raise ApiError(
            429, "TOO_MANY_REQUESTS", "A verification email was just sent. Wait a minute."
        )
    await send_verification(session, mailer, user)


async def verify_email(session: AsyncSession, token: str) -> None:
    user_id = await _consume(session, token, AuthTokenPurpose.VERIFY_EMAIL)
    await session.execute(update(User).where(User.id == user_id).values(email_verified=True))
    await session.commit()


# ---- password reset --------------------------------------------------------------------------


async def request_password_reset(session: AsyncSession, mailer: Mailer, email: str) -> None:
    """Always returns normally, whether or not the address has an account (no enumeration)."""
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active:
        return
    if await _issued_recently(session, user, AuthTokenPurpose.RESET_PASSWORD):
        return
    token = await _issue(
        session,
        user,
        AuthTokenPurpose.RESET_PASSWORD,
        timedelta(minutes=get_settings().reset_token_expire_minutes),
    )
    url = _link("/reset-password", token)
    minutes = get_settings().reset_token_expire_minutes
    await send_quietly(
        mailer,
        EmailMessage(
            to=user.email,
            subject="Reset your DocVault password",
            body=(
                f"Hi {user.name},\n\nSomeone asked to reset the password of this DocVault "
                f"account. To choose a new one, open:\n{url}\n\n"
                f"The link works once and expires in {minutes} minutes. If it wasn't you, "
                "ignore this email: your password stays as it is."
            ),
            html=render("reset_password.html", name=user.name, url=url, expire_minutes=minutes),
        ),
    )


async def reset_password(session: AsyncSession, token: str, password: str) -> None:
    user_id = await _consume(session, token, AuthTokenPurpose.RESET_PASSWORD)
    # opening the emailed link also proves the address is theirs
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=hash_password(password), email_verified=True)
    )
    # every other outstanding reset link for this account dies with this one
    await session.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == AuthTokenPurpose.RESET_PASSWORD,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=func.now())
    )
    await session.commit()
