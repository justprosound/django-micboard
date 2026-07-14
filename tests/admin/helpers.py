"""Shared model graph helpers for request-level admin smoke tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth.models import Permission
from django.contrib.sites.models import Site

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Building, Location
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership


@dataclass(frozen=True)
class TenantInventory:
    """Allowed and foreign inventory used to prove tenant isolation."""

    allowed_organization: Organization
    foreign_organization: Organization
    allowed_site: Site
    foreign_site: Site
    allowed_manufacturer: Manufacturer
    foreign_manufacturer: Manufacturer
    allowed_chassis: WirelessChassis


def grant_permissions(user: Any, *codenames: str) -> None:
    """Grant Micboard model permissions to a host-project user."""
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="micboard",
            codename__in=codenames,
        )
    )


def create_location(
    *,
    name: str,
    organization: Organization | None = None,
    campus: Campus | None = None,
    site: Site | None = None,
) -> Location:
    """Create a physical location with optional tenant scope."""
    building = Building.objects.create(
        name=f"{name} Building",
        organization_id=organization.pk if organization else None,
        campus_id=campus.pk if campus else None,
        site=site,
    )
    return Location.objects.create(building=building, name=name)


def create_chassis(
    *,
    name: str,
    manufacturer: Manufacturer,
    location: Location,
    ip: str,
    max_channels: int = 0,
) -> WirelessChassis:
    """Create deterministic managed inventory without external calls."""
    return WirelessChassis.objects.create(
        name=name,
        manufacturer=manufacturer,
        api_device_id=name.lower().replace(" ", "-"),
        role="receiver",
        location=location,
        ip=ip,
        max_channels=max_channels,
    )


def create_tenant_inventory(user: Any) -> TenantInventory:
    """Create an allowed tenant and a foreign isolation control."""
    allowed_site = Site.objects.create(domain="allowed.example.test", name="Allowed Site")
    foreign_site = Site.objects.create(domain="foreign.example.test", name="Foreign Site")
    allowed_organization = Organization.objects.create(
        name="Allowed Organization",
        slug="allowed-organization",
        site=allowed_site,
    )
    foreign_organization = Organization.objects.create(
        name="Foreign Organization",
        slug="foreign-organization",
        site=foreign_site,
    )
    allowed_campus = Campus.objects.create(
        organization=allowed_organization,
        name="Allowed Campus",
        slug="allowed-campus",
    )
    foreign_campus = Campus.objects.create(
        organization=foreign_organization,
        name="Foreign Campus",
        slug="foreign-campus",
    )
    OrganizationMembership.objects.create(
        user=user,
        organization=allowed_organization,
        campus=allowed_campus,
        role="admin",
    )

    allowed_location = create_location(
        name="Allowed Location",
        organization=allowed_organization,
        campus=allowed_campus,
        site=allowed_site,
    )
    foreign_location = create_location(
        name="Foreign Location",
        organization=foreign_organization,
        campus=foreign_campus,
        site=foreign_site,
    )
    allowed_manufacturer = Manufacturer.objects.create(
        name="Allowed Manufacturer",
        code="allowed-manufacturer",
    )
    foreign_manufacturer = Manufacturer.objects.create(
        name="Foreign Manufacturer",
        code="foreign-manufacturer",
    )
    allowed_chassis = create_chassis(
        name="Allowed Chassis",
        manufacturer=allowed_manufacturer,
        location=allowed_location,
        ip="192.0.2.10",
    )
    create_chassis(
        name="Foreign Chassis",
        manufacturer=foreign_manufacturer,
        location=foreign_location,
        ip="192.0.2.11",
    )
    return TenantInventory(
        allowed_organization=allowed_organization,
        foreign_organization=foreign_organization,
        allowed_site=allowed_site,
        foreign_site=foreign_site,
        allowed_manufacturer=allowed_manufacturer,
        foreign_manufacturer=foreign_manufacturer,
        allowed_chassis=allowed_chassis,
    )
