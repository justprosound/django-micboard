"""Multi-tenancy support models.

This module re-exports models from the micboard.multitenancy app for convenience.
The actual models are defined in micboard.multitenancy.models.
"""

from micboard.multitenancy.models import Campus, Organization, OrganizationMembership

__all__ = [
    "Campus",
    "Organization",
    "OrganizationMembership",
]
