"""Mailchimp Transactional (Mandrill) over its HTTP API, the production Mailer.

The society runs its newsletters on Mailchimp, so transactional mail goes
through the same account. The API answers 200 with a per-recipient status
even when it did not send, so the status is checked, not just the code.
"""

import logging

import httpx

from sws_membership.mail.mailer import EmailMessage

logger = logging.getLogger(__name__)
SENT_STATUSES = {"sent", "queued", "scheduled"}


class MailchimpError(Exception):
    pass


class MailchimpTransactionalMailer:
    def __init__(
        self,
        api_key: str,
        from_email: str,
        from_name: str,
        base_url: str = "https://mandrillapp.com/api/1.0",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.client = client or httpx.Client(base_url=base_url, timeout=15)

    def send(self, message: EmailMessage) -> None:
        response = self.client.post(
            "/messages/send",
            json={
                "key": self.api_key,
                "message": {
                    "from_email": self.from_email,
                    "from_name": self.from_name,
                    "to": [{"email": message.to, "type": "to"}],
                    "subject": message.subject,
                    "text": message.text,
                },
            },
        )
        if response.status_code >= 400:
            logger.error(
                "mailchimp refused a message to %s: %s %s",
                message.to,
                response.status_code,
                response.text[:200],
            )
            raise MailchimpError(response.status_code)
        results = response.json()
        if not isinstance(results, list):
            logger.error(
                "mailchimp answered unexpectedly for %s: %s", message.to, str(results)[:200]
            )
            raise MailchimpError("unexpected response")
        for result in results:
            if result.get("status") not in SENT_STATUSES:
                logger.error("mailchimp did not send to %s: %s", message.to, result)
                raise MailchimpError(result.get("reject_reason") or result.get("status"))
