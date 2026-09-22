from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import AnyUser, CurrentClaims, SessionDep
from app.core.security import create_access_token
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
    UserOut,
)
from app.schemas.common import ErrorResponse, Responses
from app.services import account_recovery, accounts
from app.services.mailer import Mailer, get_mailer

router = APIRouter(prefix="/auth", tags=["auth"])

MailerDep = Annotated[Mailer, Depends(get_mailer)]

_UNAUTHORIZED: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"}
}


@router.post(
    "/register",
    status_code=201,
    response_model=UserOut,
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}},
)
async def register(body: RegisterRequest, session: SessionDep, mailer: MailerDep) -> UserOut:
    user = await accounts.register_user(
        session, email=body.email, password=body.password, name=body.name
    )
    if not user.email_verified:
        await account_recovery.send_verification(session, mailer, user)
    return UserOut.model_validate(user)


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse, "description": "Wrong email or password"}},
)
async def login(body: LoginRequest, session: SessionDep) -> LoginResponse:
    user = await accounts.authenticate(session, email=body.email, password=body.password)
    token, _ = create_access_token(user.id)
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=204, responses=_UNAUTHORIZED)
async def logout(claims: CurrentClaims, session: SessionDep) -> Response:
    """Revoke the token used for this request. Other tokens of the same user stay valid."""
    await accounts.revoke_token(session, claims)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut, responses=_UNAUTHORIZED)
async def me(user: AnyUser) -> UserOut:
    return UserOut.model_validate(user)


_TOKEN_ERROR: Responses = {
    400: {"model": ErrorResponse, "description": "The link is invalid, used or expired"}
}


@router.post("/verify-email", status_code=204, responses=_TOKEN_ERROR)
async def verify_email(body: TokenRequest, session: SessionDep) -> Response:
    """Open the link from the verification email (FR-1). Works once."""
    await account_recovery.verify_email(session, body.token)
    return Response(status_code=204)


@router.post(
    "/resend-verification",
    status_code=204,
    responses={
        **_UNAUTHORIZED,
        429: {"model": ErrorResponse, "description": "One was just sent"},
    },
)
async def resend_verification(user: AnyUser, session: SessionDep, mailer: MailerDep) -> Response:
    await account_recovery.resend_verification(session, mailer, user)
    return Response(status_code=204)


@router.post("/forgot-password", status_code=204)
async def forgot_password(
    body: ForgotPasswordRequest, session: SessionDep, mailer: MailerDep
) -> Response:
    """Always 204, whether or not the address has an account (FR-4)."""
    await account_recovery.request_password_reset(session, mailer, body.email)
    return Response(status_code=204)


@router.post("/reset-password", status_code=204, responses=_TOKEN_ERROR)
async def reset_password(body: ResetPasswordRequest, session: SessionDep) -> Response:
    """Choose a new password with the emailed token (FR-4). Works once."""
    await account_recovery.reset_password(session, body.token, body.password)
    return Response(status_code=204)
