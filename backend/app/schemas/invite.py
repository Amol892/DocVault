from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import Email


class InviteCreate(BaseModel):
    email: Email
    # "owner" is never accepted: ownership only moves through transfer-ownership
    role: Literal["admin", "member", "guest"]
    # for a Guest: the documents they can see once they accept (FR-21); ignored for other roles
    document_ids: list[str] = Field(default_factory=list, max_length=200)


class InviteOut(BaseModel):
    id: str
    email: str
    role: Literal["admin", "member", "guest"]
    expires_at: datetime
    created_at: datetime
    expired: bool
    # only in the response that creates the invite: the server keeps just a hash of the token
    url: str | None = None
    # whether the email went out; when false the admin can hand over `url` instead
    email_sent: bool | None = None


class InvitePreviewOut(BaseModel):
    """What the person holding the link sees before accepting."""

    workspace_name: str
    role: Literal["admin", "member", "guest"]
    email: str
    expired: bool
