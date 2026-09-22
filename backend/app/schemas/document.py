from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.folder import EntryName

# `type/subtype` with an optional parameter, e.g. text/plain; charset=utf-8
MimeType = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=127,
        pattern=r"^[A-Za-z0-9][\w.+-]*/[A-Za-z0-9][\w.+-]*(\s*;.*)?$",
    ),
]


class UploadUrlRequest(BaseModel):
    filename: EntryName
    mime_type: MimeType
    size_bytes: int = Field(ge=1)
    # both null = a personal document
    workspace_id: str | None = None
    folder_id: str | None = None
    # set to add a NEW VERSION to an existing document instead of creating a document
    document_id: str | None = None


class UploadUrlResponse(BaseModel):
    upload_url: str
    storage_key: str
    document_id: str


class DownloadUrlResponse(BaseModel):
    download_url: str
    expires_in: int


class PreviewUrlResponse(BaseModel):
    preview_url: str
    expires_in: int


class DocumentPatch(BaseModel):
    """Exactly one of `filename` (rename) or `folder_id` (move; null = the workspace root)."""

    filename: EntryName | None = None
    folder_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_field(self) -> Self:
        provided = self.model_fields_set & {"filename", "folder_id"}
        if len(provided) != 1:
            raise ValueError("send exactly one of filename or folder_id")
        if "filename" in provided and self.filename is None:
            raise ValueError("filename must not be null")
        return self


class DocumentOut(BaseModel):
    id: str
    owner_id: str
    owner_name: str
    workspace_id: str | None
    folder_id: str | None
    filename: str
    # from the document's current version (the highest-numbered ready one)
    mime_type: str
    size_bytes: int
    visibility: Literal["private", "workspace", "public"]
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GrantCreate(BaseModel):
    user_id: str


class DocumentVersionOut(BaseModel):
    version_number: int
    size_bytes: int
    mime_type: str
    created_by_name: str
    created_at: datetime
    is_current: bool
