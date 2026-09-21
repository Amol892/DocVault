from functools import lru_cache

from app.config import get_settings
from app.storage.base import StorageBackend, StorageConfigError
from app.storage.s3_backend import S3Backend


@lru_cache
def _s3_backend() -> S3Backend:
    settings = get_settings()
    return S3Backend(
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=settings.s3_public_base,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
    )


def get_storage() -> StorageBackend:
    """FastAPI dependency: the configured object storage (tests override it)."""
    backend = get_settings().storage_backend
    if backend == "s3":
        return _s3_backend()
    raise StorageConfigError(
        f"STORAGE_BACKEND={backend!r} is not implemented yet; use 's3' (MinIO or any S3 service)."
    )
