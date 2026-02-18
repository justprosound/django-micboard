"""Service logic for Organization and OrganizationMembership admin behaviors."""


def get_device_count(organization):
    """Return the device count for an organization."""
    return organization.get_device_count()


def set_created_by(obj, user):
    """Set created_by field on a new OrganizationMembership object."""
    obj.created_by = user
    return obj
