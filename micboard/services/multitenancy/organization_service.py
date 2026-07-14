"""Service logic for Organization and OrganizationMembership admin behaviors."""


def get_device_count(organization):
    """Return the device count for an organization."""
    from micboard.models.hardware.wireless_chassis import WirelessChassis

    return WirelessChassis.objects.filter(
        location__building__organization_id=organization.pk,
    ).count()


def is_at_device_limit(organization) -> bool:
    """Return whether an organization reached its configured device limit."""
    if organization.max_devices is None:
        return False
    return get_device_count(organization) >= organization.max_devices


def set_created_by(obj, user):
    """Set created_by field on a new OrganizationMembership object."""
    obj.created_by = user
    return obj
