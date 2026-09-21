import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    content_type: str | None


class StorageBackend(Protocol):
    """Object storage. File bytes never pass through the API: it only hands out short-lived
    pre-signed URLs (after the authorization check) and inspects objects the browser uploaded."""

    async def presign_upload(
        self, key: str, *, content_type: str, size_bytes: int, expires_seconds: int
    ) -> str: ...

    async def presign_download(
        self, key: str, *, filename: str, content_type: str, expires_seconds: int
    ) -> str: ...

    async def head(self, key: str) -> ObjectInfo | None: ...

    async def read_prefix(self, key: str, length: int) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    def object_url(self, key: str) -> str:
        """The object's full address (informational; the bucket is private)."""
        ...


class StorageConfigError(RuntimeError):
    """The storage backend is not usable as configured."""


def content_disposition(filename: str) -> str:
    """A safe `attachment` Content-Disposition for a user-supplied filename.

    `attachment` makes the browser download instead of rendering, so an uploaded HTML or SVG file
    can never run as script on the storage origin. Control characters, quotes, backslashes and
    path separators are removed; non-ASCII names use the RFC 5987 `filename*` form with an ASCII
    fallback.
    """
    cleaned = re.sub(r'[\x00-\x1f\x7f"\\/]', "", filename).strip() or "download"
    fallback = re.sub(r"[^\x20-\x7e]", "_", cleaned)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(cleaned, safe='')}"
