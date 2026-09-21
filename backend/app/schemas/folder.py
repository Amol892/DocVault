import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, StringConstraints

_FORBIDDEN = re.compile(r"[/\\\x00-\x1f\x7f]")


def _no_path_characters(value: str) -> str:
    if _FORBIDDEN.search(value):
        raise ValueError("must not contain / or \\ or control characters")
    return value


# A name shown in the UI and used in file listings: never a path, never empty
EntryName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(_no_path_characters),
]


class FolderCreate(BaseModel):
    name: EntryName
    parent_folder_id: str | None = None


class FolderRename(BaseModel):
    name: EntryName


class FolderOut(BaseModel):
    id: str
    workspace_id: str | None
    parent_folder_id: str | None
    name: str


class GrantCreate(BaseModel):
    user_id: str
