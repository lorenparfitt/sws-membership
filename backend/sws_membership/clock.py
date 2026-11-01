"""The calendar day the platform acts on, as one function tests can pin."""

from datetime import date

from django.utils import timezone


def today() -> date:
    return timezone.localdate()
