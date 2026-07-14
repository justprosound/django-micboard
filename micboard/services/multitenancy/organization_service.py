"""Service logic for Organization and OrganizationMembership admin behaviors."""

from typing import Any


def get_device_count(organization: Any) -> int:
    """Return the device count for an organization."""
    from micboard.models.hardware.wireless_chassis import WirelessChassis

    return WirelessChassis.objects.filter(
        location__building__organization_id=organization.pk,
    ).count()


def set_created_by(obj: Any, user: Any) -> Any:
    """Set created_by field on a new OrganizationMembership object."""
    obj.created_by = user
    return obj
