"""Settings validation that must fail fast at startup, not at first use."""

import pytest

from app.config import Settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
    "S3_ENDPOINT_URL": "http://x",
    "S3_ACCESS_KEY": "x",
    "S3_SECRET_KEY": "x",
    "JWT_SECRET": "x" * 32,
}


def settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for key, value in {**REQUIRED_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)
    # ignore the developer's real .env: this test must only see what it sets above
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_the_default_smtp_from_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings(monkeypatch).smtp_from == "DocVault <no-reply@example.com>"


@pytest.mark.parametrize(
    "value",
    [
        "shewalkar.amol892gmail.com",  # the real value from the bug report: no @ at all
        "not-an-email",
        "",
        "DocVault <not-an-email>",
        "a@b",  # no TLD
    ],
)
def test_a_malformed_smtp_from_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    with pytest.raises(ValueError, match="SMTP_FROM"):
        settings(monkeypatch, SMTP_FROM=value)


@pytest.mark.parametrize(
    "value",
    [
        "no-reply@example.com",
        "DocVault <no-reply@example.com>",
        "Resend Test <onboarding@resend.dev>",
    ],
)
def test_a_well_formed_smtp_from_is_accepted(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    assert settings(monkeypatch, SMTP_FROM=value).smtp_from == value
