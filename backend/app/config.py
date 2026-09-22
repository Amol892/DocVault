from email.utils import parseaddr
from functools import lru_cache
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from pydantic import Field, field_validator
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
    # How long a soft-deleted document stays restorable before the purge job removes it for good.
    trash_grace_days: int = Field(default=30, gt=0)
    # An upload that was never confirmed is abandoned after this long.
    pending_upload_ttl_hours: int = Field(default=24, gt=0)
    frontend_url: str = "http://localhost:5173"
    # FR-1: new accounts must confirm their email address before they can use the API.
    require_email_verification: bool = True
    verify_token_expire_hours: int = Field(default=24, gt=0)
    reset_token_expire_minutes: int = Field(default=60, gt=0)
    # Minimum gap between two verification / reset emails for the same account.
    token_cooldown_seconds: int = Field(default=60, ge=0)
    # Invitations expire after this many days.
    invite_expire_days: int = Field(default=7, gt=0)
    # Outgoing email. Without smtp_host nothing is sent: messages are logged instead (development).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "DocVault <no-reply@example.com>"
    smtp_starttls: bool = True  # upgrade a plain connection with STARTTLS (port 587)
    smtp_ssl: bool = False  # implicit TLS from the start (port 465); overrides smtp_starttls

    @field_validator("smtp_from")
    @classmethod
    def _smtp_from_is_a_valid_address(cls, value: str) -> str:
        """Catches a malformed SMTP_FROM at startup instead of on the first email: with a bad
        sender address, every send fails with the same SMTPSenderRefused, silently (FR-4's
        forgot-password always answers 204), so it would otherwise go unnoticed until someone
        checked the logs."""
        _, address = parseaddr(value)
        if not address:
            raise ValueError(
                f"SMTP_FROM={value!r} has no email address. Use a plain address or "
                "'Name <address@example.com>'."
            )
        try:
            validate_email(address, check_deliverability=False)
        except EmailNotValidError as exc:
            raise ValueError(f"SMTP_FROM={value!r} is not a valid email address: {exc}") from exc
        return value

    @property
    def s3_public_base(self) -> str:
        return (self.s3_public_endpoint_url or self.s3_endpoint_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
