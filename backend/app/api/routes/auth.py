from fastapi import APIRouter, Response

from app.api.deps import CurrentClaims, CurrentUser, SessionDep
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserOut
from app.schemas.common import ErrorResponse, Responses
from app.services import accounts

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED: Responses = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or revoked token"}
}


@router.post(
    "/register",
    status_code=201,
    response_model=UserOut,
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}},
)
async def register(body: RegisterRequest, session: SessionDep) -> UserOut:
    user = await accounts.register_user(
        session, email=body.email, password=body.password, name=body.name
    )
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
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
