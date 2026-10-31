"""A placeholder waiver for development. Not legal text; the society supplies that."""

from sqlalchemy.orm import Session

from sws_membership.waivers.service import current_template, publish_template

PLACEHOLDER_TITLE = "Squamish Windsports Society release of liability (development placeholder)"
PLACEHOLDER_BODY = """This is placeholder text for development and testing only. It is not the
society's waiver and carries no legal effect.

The real waiver text is published by an administrator before launch, and
every member signs it before buying a pass that requires it.
"""


def load_sample_waiver(session: Session) -> bool:
    """Publish the placeholder if no template exists; return whether it did."""
    if current_template(session) is not None:
        return False
    publish_template(session, PLACEHOLDER_TITLE, PLACEHOLDER_BODY, by=None)
    return True
