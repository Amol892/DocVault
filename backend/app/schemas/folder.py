import re
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, StringConstraints, model_validator

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


class FolderPatch(BaseModel):
    """Exactly one of `name` (rename) or `parent_folder_id` (move; null = the workspace root)."""

    name: EntryName | None = None
    parent_folder_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_field(self) -> Self:
        provided = self.model_fields_set & {"name", "parent_folder_id"}
        if len(provided) != 1:
            raise ValueError("send exactly one of name or parent_folder_id")
        if "name" in provided and self.name is None:
            raise ValueError("name must not be null")
        return self


class FolderOut(BaseModel):
    id: str
    workspace_id: str | None
    parent_folder_id: str | None
    name: str
