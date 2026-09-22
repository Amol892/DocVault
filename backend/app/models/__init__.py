"""Import every model so Base.metadata is complete (alembic/env.py imports this package)."""

from app.models.activity import ActivityLog
from app.models.auth_token import AuthToken
from app.models.document import Document, DocumentGrant, DocumentVersion
from app.models.folder import Folder
from app.models.revoked_token import RevokedToken
from app.models.share_link import ShareLink, ShareLinkAccessLog
from app.models.user import User
from app.models.workspace import (
    Workspace,
    WorkspaceInvite,
    WorkspaceInviteDocument,
    WorkspaceMember,
)

__all__ = [
    "ActivityLog",
    "AuthToken",
    "Document",
    "DocumentGrant",
    "DocumentVersion",
    "Folder",
    "RevokedToken",
    "ShareLink",
    "ShareLinkAccessLog",
    "User",
    "Workspace",
    "WorkspaceInvite",
    "WorkspaceInviteDocument",
    "WorkspaceMember",
]
