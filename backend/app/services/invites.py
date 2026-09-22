"""Workspace invitations (FR-18, FR-21).

An invite carries a role (never Owner) and, for a Guest, the documents they will be granted. The
token is 256 random bits and only its SHA-256 hash is stored. Accepting needs a signed-in account
whose email is the one invited, so a forwarded link is useless to anyone else.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ApiError, not_found
from app.models.document import DocumentGrant
from app.models.enums import WorkspaceRole
from app.models.user import User
from app.models.workspace import (
    Workspace,
    WorkspaceInvite,
    WorkspaceInviteDocument,
    WorkspaceMember,
)
from app.schemas.invite import InviteCreate, InviteOut, InvitePreviewOut
from app.services import activity
from app.services.access import WorkspaceAccess, get_live_document
from app.services.email_templates import render
from app.services.mailer import EmailMessage, Mailer, send_quietly

TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _out(invite: WorkspaceInvite, *, url: str | None = None, sent: bool | None = None) -> InviteOut:
    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        expired=invite.expires_at <= datetime.now(UTC),
        url=url,
        email_sent=sent,
    )


def _pending(workspace_id: str):  # type: ignore[no-untyped-def]
    return (
        WorkspaceInvite.workspace_id == workspace_id,
        WorkspaceInvite.accepted_at.is_(None),
        WorkspaceInvite.revoked_at.is_(None),
    )


async def create_invite(
    session: AsyncSession, mailer: Mailer, access: WorkspaceAccess, body: InviteCreate
) -> InviteOut:
    workspace = access.workspace
    existing_member = (
        await session.execute(
            select(WorkspaceMember.id)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(
                WorkspaceMember.workspace_id == workspace.id,
                func.lower(User.email) == body.email.lower(),
            )
        )
    ).first()
    if existing_member is not None:
        raise ApiError(409, "ALREADY_MEMBER", "This person is already a member of the workspace.")

    now = datetime.now(UTC)
    pending = (
        await session.execute(
            select(WorkspaceInvite).where(
                *_pending(workspace.id), func.lower(WorkspaceInvite.email) == body.email.lower()
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        if pending.expires_at > now:
            raise ApiError(
                409,
                "INVITE_PENDING",
                "This person already has a pending invite. Revoke it to send a new one.",
            )
        pending.revoked_at = now  # an expired invite no longer blocks a fresh one
        await session.flush()

    document_ids = list(dict.fromkeys(body.document_ids)) if body.role == "guest" else []
    for document_id in document_ids:
        if await get_live_document(session, workspace.id, document_id) is None:
            raise not_found("Document not found.")

    token = secrets.token_urlsafe(TOKEN_BYTES)
    invite = WorkspaceInvite(
        workspace_id=workspace.id,
        email=body.email,
        role=body.role,
        token_hash=hash_token(token),
        invited_by=access.user.id,
        expires_at=now + timedelta(days=get_settings().invite_expire_days),
    )
    session.add(invite)
    await session.flush()
    for document_id in document_ids:
        session.add(WorkspaceInviteDocument(invite_id=invite.id, document_id=document_id))
    activity.record_activity(
        session,
        workspace_id=workspace.id,
        actor_id=access.user.id,
        action=activity.MEMBER_INVITED,
        target_type="invite",
        target_id=invite.id,
        metadata={"email": body.email, "role": body.role},
    )
    try:
        await session.commit()
    except IntegrityError as exc:  # two admins inviting the same address at once
        await session.rollback()
        if "uq_workspace_invites_pending" in str(exc.orig):
            raise ApiError(
                409, "INVITE_PENDING", "This person already has a pending invite."
            ) from exc
        raise

    url = f"{get_settings().frontend_url.rstrip('/')}/invites/{token}"
    expire_days = get_settings().invite_expire_days
    sent = await send_quietly(
        mailer,
        EmailMessage(
            to=body.email,
            subject=f"{access.user.name} invited you to {workspace.name} on DocVault",
            body=(
                f'{access.user.name} invited you to join the workspace "{workspace.name}" '
                f"as {body.role}.\n\nOpen this link to accept (sign in or create an account "
                f"with this email address first):\n{url}\n\n"
                f"The invitation expires in {expire_days} days."
            ),
            html=render(
                "invite.html",
                inviter_name=access.user.name,
                workspace_name=workspace.name,
                role=body.role,
                url=url,
                expire_days=expire_days,
            ),
        ),
    )
    return _out(invite, url=url, sent=sent)


async def list_invites(session: AsyncSession, workspace_id: str) -> list[InviteOut]:
    rows = await session.execute(
        select(WorkspaceInvite)
        .where(*_pending(workspace_id))
        .order_by(WorkspaceInvite.created_at.desc(), WorkspaceInvite.id)
    )
    return [_out(invite) for invite in rows.scalars()]


async def revoke_invite(session: AsyncSession, access: WorkspaceAccess, invite_id: str) -> None:
    invite = (
        await session.execute(
            select(WorkspaceInvite).where(
                WorkspaceInvite.id == invite_id, *_pending(access.workspace.id)
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        raise not_found("Invite not found.")
    invite.revoked_at = datetime.now(UTC)
    activity.record_activity(
        session,
        workspace_id=access.workspace.id,
        actor_id=access.user.id,
        action=activity.INVITE_REVOKED,
        target_type="invite",
        target_id=invite.id,
        metadata={"email": invite.email},
    )
    await session.commit()


async def _find(session: AsyncSession, token: str) -> tuple[WorkspaceInvite, Workspace]:
    row = (
        await session.execute(
            select(WorkspaceInvite, Workspace)
            .join(Workspace, Workspace.id == WorkspaceInvite.workspace_id)
            .where(WorkspaceInvite.token_hash == hash_token(token), Workspace.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        raise not_found("This invitation doesn't exist.")
    return row[0], row[1]


def _check_usable(invite: WorkspaceInvite) -> None:
    if invite.revoked_at is not None:
        raise ApiError(410, "INVITE_REVOKED", "This invitation was revoked.")
    if invite.expires_at <= datetime.now(UTC):
        raise ApiError(410, "INVITE_EXPIRED", "This invitation has expired.")


async def preview_invite(session: AsyncSession, token: str) -> InvitePreviewOut:
    invite, workspace = await _find(session, token)
    if invite.accepted_at is not None:
        raise ApiError(410, "INVITE_USED", "This invitation was already accepted.")
    _check_usable(invite)
    return InvitePreviewOut(
        workspace_name=workspace.name,
        role=invite.role,
        email=invite.email,
        expired=False,
    )


async def accept_invite(session: AsyncSession, user: User, token: str) -> None:
    invite, workspace = await _find(session, token)
    membership = (
        await session.execute(
            select(WorkspaceMember.id).where(
                WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id
            )
        )
    ).first()
    if invite.accepted_at is not None:
        if membership is not None:  # accepting twice is harmless
            return
        raise ApiError(410, "INVITE_USED", "This invitation was already accepted.")
    _check_usable(invite)
    if invite.email.lower() != user.email.lower():
        raise ApiError(
            403,
            "INVITE_EMAIL_MISMATCH",
            "This invitation was sent to a different email address.",
        )

    invite.accepted_at = datetime.now(UTC)
    if membership is None:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole(invite.role),
                invited_by=invite.invited_by,
            )
        )
        if invite.role == WorkspaceRole.GUEST:
            document_ids = (
                (
                    await session.execute(
                        select(WorkspaceInviteDocument.document_id).where(
                            WorkspaceInviteDocument.invite_id == invite.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            for document_id in document_ids:
                if await get_live_document(session, workspace.id, document_id) is not None:
                    session.add(
                        DocumentGrant(
                            workspace_id=workspace.id,
                            document_id=document_id,
                            user_id=user.id,
                            granted_by=invite.invited_by,
                        )
                    )
        activity.record_activity(
            session,
            workspace_id=workspace.id,
            actor_id=user.id,
            action=activity.MEMBER_JOINED,
            target_type="user",
            target_id=user.id,
            metadata={"role": invite.role},
        )
    try:
        await session.commit()
    except IntegrityError:  # joined in a parallel request: the outcome is the same
        await session.rollback()
