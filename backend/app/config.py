from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent

# Absolute paths, so the result does not depend on the directory a command is run from.
# Later files override earlier ones, and real environment variables override both:
#   1. <repo>/.env         the one place settings are defined; host-oriented (127.0.0.1). Docker
#                          Compose overrides DATABASE_URL / S3_ENDPOINT_URL for the containers.
#   2. <repo>/backend/.env optional per-machine override; normally not needed
ENV_FILES = (ROOT_DIR / ".env", BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    database_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    # Address the browser can reach, used to sign pre-signed URLs (signatures are host-bound).
    # Defaults to s3_endpoint_url; in Docker they differ (storage:9000 vs localhost:9000).
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "docvault"
    storage_backend: str = "s3"  # s3 | local
    upload_url_expire_seconds: int = Field(default=900, gt=0)
    download_url_expire_seconds: int = Field(default=300, gt=0)
    # HS256 signing key: long enough that it cannot be brute-forced (>= 32 characters).
    jwt_secret: str = Field(min_length=32)
    # Access-token lifetime. There is no refresh flow, so expiry means logging in again.
    jwt_expire_minutes: int = Field(default=1440, gt=0)
    max_upload_mb: int = 100
    frontend_url: str = "http://localhost:5173"

    @property
    def s3_public_base(self) -> str:
        return (self.s3_public_endpoint_url or self.s3_endpoint_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
