"""Every model module, imported so Base.metadata describes the whole schema.

Alembic autogenerate and the test database both work from this metadata, so
a new model module is registered here and nowhere else.
"""

from sws_membership.database import Base
from sws_membership.members import member_numbers, models  # noqa: F401

metadata = Base.metadata
