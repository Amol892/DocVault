from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import WorkspaceRole
from app.schemas.auth import PersonName


class WorkspaceCreate(BaseModel):
    name: PersonName


class WorkspaceSummaryOut(BaseModel):
    id: str
    name: str
    role: WorkspaceRole


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    owner_id: str
    created_at: datetime
    # The caller's own role. The frontend needs it for every screen, and a Guest cannot fetch the
    # member list to work it out.
    my_role: WorkspaceRole


class MemberOut(BaseModel):
    user_id: str
    name: str
    email: str
    role: WorkspaceRole
    joined_at: datetime
    # Only present for guests: the documents they were granted (document_grants, FR-21)
    granted_document_ids: list[str] | None = None


class RoleChange(BaseModel):
    # "owner" is never accepted here: ownership only moves through transfer-ownership
    role: Literal[WorkspaceRole.ADMIN, WorkspaceRole.MEMBER, WorkspaceRole.GUEST]
