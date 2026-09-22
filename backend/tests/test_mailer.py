"""The real mailers, without a network: SMTP is replaced by a recording stub."""

import logging
import smtplib
from typing import Any

import pytest

from app.services.mailer import EmailMessage, LogMailer, SmtpMailer, send_quietly

MESSAGE = EmailMessage(
    to="a@example.com",
    subject="Hello",
    body="Link: https://x/y",
    html="<p>Link: <a href='https://x/y'>https://x/y</a></p>",
)


class StubSmtp:
    instances: list["StubSmtp"] = []

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host, self.port, self.calls = host, port, []
        StubSmtp.instances.append(self)

    def __enter__(self) -> "StubSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self, **kwargs: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user}")

    def send_message(self, message: Any) -> None:
        self.calls.append(("send", message["To"], message["From"], message["Subject"]))
        self.sent_message = message


def mailer(**over: Any) -> SmtpMailer:
    args: dict[str, Any] = {
        "host": "smtp.test",
        "port": 587,
        "username": "user",
        "password": "pw",
        "sender": "DocVault <no-reply@test>",
        "starttls": True,
        "use_ssl": False,
    }
    return SmtpMailer(**{**args, **over})


async def test_smtp_mailer_upgrades_to_tls_logs_in_and_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubSmtp.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", StubSmtp)
    await mailer().send(MESSAGE)
    (server,) = StubSmtp.instances
    assert (server.host, server.port) == ("smtp.test", 587)
    assert server.calls == [
        "starttls",
        "login user",
        ("send", "a@example.com", "DocVault <no-reply@test>", "Hello"),
    ]
    assert server.sent_message.is_multipart()
    parts = {
        part.get_content_type(): part.get_content()
        for part in server.sent_message.walk()
        if not part.is_multipart()
    }
    assert "Link: https://x/y" in parts["text/plain"]
    assert "https://x/y" in parts["text/html"]


async def test_smtp_without_credentials_does_not_log_in(monkeypatch: pytest.MonkeyPatch) -> None:
    StubSmtp.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", StubSmtp)
    await mailer(username=None, password=None, starttls=False).send(MESSAGE)
    assert StubSmtp.instances[0].calls == [
        ("send", "a@example.com", "DocVault <no-reply@test>", "Hello")
    ]


async def test_implicit_tls_uses_smtp_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    used: list[str] = []

    class SslStub(StubSmtp):
        def __init__(self, host: str, port: int, **kwargs: Any) -> None:
            super().__init__(host, port)
            used.append("ssl")

    monkeypatch.setattr(smtplib, "SMTP_SSL", SslStub)
    await mailer(port=465, use_ssl=True).send(MESSAGE)
    assert used == ["ssl"]


async def test_log_mailer_writes_the_message_to_the_log(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        await LogMailer().send(MESSAGE)
    assert "https://x/y" in caplog.text and "nothing was sent" in caplog.text


async def test_send_quietly_reports_failure_without_leaking_the_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Broken:
        async def send(self, message: EmailMessage) -> None:
            raise ConnectionError("boom")

    with caplog.at_level(logging.ERROR):
        assert await send_quietly(Broken(), MESSAGE) is False
    assert "a@example.com" in caplog.text
    assert "https://x/y" not in caplog.text  # the body/html can hold a credential-bearing link
