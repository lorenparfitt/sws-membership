"""Every model module, imported so Base.metadata describes the whole schema.

Alembic autogenerate and the test database both work from this metadata, so
a new model module is registered here and nowhere else.
"""

from sws_membership.auth import models as auth_models  # noqa: F401
from sws_membership.catalog import models as catalog_models  # noqa: F401
from sws_membership.database import Base
from sws_membership.entitlements import models as entitlement_models  # noqa: F401
from sws_membership.members import member_numbers  # noqa: F401
from sws_membership.members import models as member_models  # noqa: F401
from sws_membership.orders import models as order_models  # noqa: F401

metadata = Base.metadata
