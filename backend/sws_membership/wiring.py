"""The configured implementations behind the three seams: mail, storage, payments.

Built once from settings on first use. Tests replace an attribute for the
duration of a test; nothing else in the code base reads settings for these.
"""

from pathlib import Path

from django.conf import settings


class Wiring:
    def __init__(self) -> None:
        self._mailer = None
        self._storage = None
        self._processor = None

    @property
    def mailer(self):
        if self._mailer is None:
            from sws_membership.mail.mailchimp import MailchimpTransactionalMailer
            from sws_membership.mail.mailer import ConsoleMailer

            if settings.SWS_MAIL_BACKEND == "mailchimp":
                self._mailer = MailchimpTransactionalMailer(
                    api_key=settings.SWS_MAILCHIMP_TRANSACTIONAL_API_KEY,
                    from_email=settings.SWS_MAIL_FROM_EMAIL,
                    from_name=settings.SWS_MAIL_FROM_NAME,
                )
            else:
                self._mailer = ConsoleMailer()
        return self._mailer

    @mailer.setter
    def mailer(self, value) -> None:
        self._mailer = value

    @property
    def storage(self):
        if self._storage is None:
            from sws_membership.storage.objects import LocalDirectoryStorage

            self._storage = LocalDirectoryStorage(Path(settings.SWS_STORAGE_DIRECTORY))
        return self._storage

    @storage.setter
    def storage(self, value) -> None:
        self._storage = value

    @property
    def processor(self):
        if self._processor is None:
            from sws_membership.payments.fake import FakeProcessor
            from sws_membership.payments.nuvei import NuveiProcessor

            if settings.SWS_PAYMENT_PROCESSOR == "nuvei":
                self._processor = NuveiProcessor(
                    merchant_id=settings.SWS_NUVEI_MERCHANT_ID,
                    merchant_site_id=settings.SWS_NUVEI_MERCHANT_SITE_ID,
                    secret_key=settings.SWS_NUVEI_SECRET_KEY,
                    environment=settings.SWS_NUVEI_ENVIRONMENT,
                    notification_url=settings.SWS_NUVEI_NOTIFICATION_URL,
                )
            else:
                self._processor = FakeProcessor()
        return self._processor

    @processor.setter
    def processor(self, value) -> None:
        self._processor = value


wiring = Wiring()
