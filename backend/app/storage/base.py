from typing import Protocol


class StorageBackend(Protocol):
    """Abstraction over object storage; bytes never pass through the API."""

    async def presign_upload(self, key: str, expires_seconds: int = 300) -> str: ...

    async def presign_download(self, key: str, expires_seconds: int = 300) -> str: ...

    async def delete(self, key: str) -> None: ...
