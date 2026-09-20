from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


# Emails are stored lower-cased (the database also enforces uniqueness on lower(email)).
Email = Annotated[EmailStr, BeforeValidator(_strip), AfterValidator(str.lower)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class RegisterRequest(BaseModel):
    email: Email
    # max_length bounds the work an attacker can force Argon2 to do
    password: str = Field(min_length=8, max_length=128)
    name: PersonName


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str


class LoginResponse(BaseModel):
    token: str
    user: UserOut
