"""Import every model so Base.metadata is complete (alembic/env.py imports this package)."""

from app.models.activity import ActivityLog
from app.models.document import Document, DocumentVersion
from app.models.folder import Folder, FolderGrant
from app.models.share_link import ShareLink, ShareLinkAccessLog
from app.models.user import User
from app.models.workspace import (
    Workspace,
    WorkspaceInvite,
    WorkspaceInviteFolder,
    WorkspaceMember,
)

__all__ = [
    "ActivityLog",
    "Document",
    "DocumentVersion",
    "Folder",
    "FolderGrant",
    "ShareLink",
    "ShareLinkAccessLog",
    "User",
    "Workspace",
    "WorkspaceInvite",
    "WorkspaceInviteFolder",
    "WorkspaceMember",
]
