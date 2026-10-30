"""The one way the application sends email.

Development prints messages to the log so a sign-in link can be copied from
the console. Production swaps in a Mailgun implementation of the same
protocol at wiring time.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ConsoleMailer:
    def send(self, message: EmailMessage) -> None:
        logger.info("email to %s: %s\n%s", message.to, message.subject, message.text)
