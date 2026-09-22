"""The HTML email templates render, escape untrusted values, and carry the link."""

import pytest

from app.services.email_templates import render


def test_verify_email_renders_the_link_and_escapes_the_name() -> None:
    html = render(
        "verify_email.html",
        name="<script>alert(1)</script>",
        url="https://vault.example/verify-email/tok123",
        expire_hours=24,
    )
    assert "https://vault.example/verify-email/tok123" in html
    assert "24 hours" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_reset_password_renders_the_link() -> None:
    html = render(
        "reset_password.html",
        name="Ana",
        url="https://vault.example/reset-password/tok",
        expire_minutes=60,
    )
    assert "https://vault.example/reset-password/tok" in html
    assert "60 minutes" in html


def test_invite_renders_and_escapes_the_workspace_name() -> None:
    html = render(
        "invite.html",
        inviter_name="Ada",
        workspace_name="<b>Evil</b> Corp",
        role="guest",
        url="https://vault.example/invites/tok",
        expire_days=7,
    )
    assert "https://vault.example/invites/tok" in html
    assert "guest" in html and "Ada" in html
    assert "<b>Evil</b>" not in html
    assert "&lt;b&gt;Evil&lt;/b&gt;" in html


@pytest.mark.parametrize("template", ["verify_email.html", "reset_password.html", "invite.html"])
def test_every_template_extends_the_shared_layout(template: str) -> None:
    html = render(
        template,
        name="Ana",
        url="https://x/y",
        expire_hours=1,
        expire_minutes=1,
        expire_days=1,
        inviter_name="Ada",
        workspace_name="Acme",
        role="member",
    )
    assert "DocVault" in html
    assert "<html>" in html.lower()
