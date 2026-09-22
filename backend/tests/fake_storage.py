"""An in-memory StorageBackend for the API tests. `put` plays the browser's part of an upload: it
stores bytes under the key found in a pre-signed URL, exactly as MinIO would after the PUT."""

from urllib.parse import parse_qs, quote, unquote, urlparse

from app.storage.base import ObjectInfo, content_disposition


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str | None]] = {}
        self.deleted: list[str] = []

    async def presign_upload(
        self, key: str, *, content_type: str, size_bytes: int, expires_seconds: int
    ) -> str:
        return (
            f"http://storage.test/{quote(key)}?op=put"
            f"&type={quote(content_type, safe='')}&size={size_bytes}&expires={expires_seconds}"
        )

    async def presign_download(
        self,
        key: str,
        *,
        filename: str,
        content_type: str,
        expires_seconds: int,
        inline: bool = False,
    ) -> str:
        disposition = quote(content_disposition(filename, inline=inline), safe="")
        return (
            f"http://storage.test/{quote(key)}?op=get&disposition={disposition}"
            f"&expires={expires_seconds}"
        )

    async def head(self, key: str) -> ObjectInfo | None:
        if key not in self.objects:
            return None
        data, content_type = self.objects[key]
        return ObjectInfo(size_bytes=len(data), content_type=content_type)

    async def read_prefix(self, key: str, length: int) -> bytes:
        return self.objects[key][0][:length]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)

    def object_url(self, key: str) -> str:
        return f"http://storage.test/{key}"

    def put(self, upload_url: str, data: bytes, content_type: str | None = None) -> str:
        """Store `data` as the browser would after a PUT to `upload_url`; returns the key.
        `content_type` defaults to the one the URL was signed for."""
        parsed = urlparse(upload_url)
        signed_type = parse_qs(parsed.query)["type"][0]
        key = unquote(parsed.path.lstrip("/"))
        self.objects[key] = (data, content_type or signed_type)
        return key
