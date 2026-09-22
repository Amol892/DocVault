from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

LinkPassword = Annotated[str, StringConstraints(min_length=4, max_length=128)]


class ShareLinkCreate(BaseModel):
    allow_download: bool = True
    password: LinkPassword | None = None
    expires_at: datetime | None = None


class ShareLinkPatch(BaseModel):
    """The only setting changeable after creation. The password and expiry stay fixed for the
    life of a link — revoke it and create a new one to change those."""

    allow_download: bool


class ShareLinkOut(BaseModel):
    id: str
    document_id: str
    # only in the response that creates the link: the server keeps just a hash of the token
    url: str | None = None
    allow_download: bool
    has_password: bool
    expires_at: datetime | None
    expired: bool
    revoked_at: datetime | None
    created_at: datetime


class ShareAccessLogOut(BaseModel):
    accessed_at: datetime
    ip_address: str | None
    user_agent: str | None
    outcome: str


class PublicShareRequest(BaseModel):
    password: Annotated[str, Field(max_length=128)] | None = None


class PublicShareOut(BaseModel):
    """Everything a link recipient gets, and nothing else (FR-15): no owner, folder or workspace
    details. While a password is still needed only `requires_password` is set."""

    requires_password: bool
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    allow_download: bool | None = None
    expires_at: datetime | None = None
    download_url: str | None = None
    preview_url: str | None = None
