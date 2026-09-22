"""An in-memory Mailer for the API tests: keeps what would have been sent."""

import re

from app.services.mailer import EmailMessage


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = False  # simulate an SMTP outage

    async def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise ConnectionError("SMTP is down")
        self.sent.append(message)

    def last_link(self, marker: str) -> str:
        """The first URL in the newest message whose path contains `marker` (e.g. /invites/)."""
        for message in reversed(self.sent):
            found = re.search(rf"https?://\S*{re.escape(marker)}\S*", message.body)
            if found:
                return found.group(0)
        raise AssertionError(f"no email with a {marker} link was sent")
