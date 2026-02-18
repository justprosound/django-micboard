"""Multi-tenancy models for MSP deployments.

These models are only active when MICBOARD_MSP_ENABLED = True.
They provide organization and campus hierarchy for multi-tenant scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models

if TYPE_CHECKING:
    pass


class Organization(models.Model):
    """Top-level tenant entity for MSP deployments.

    Examples:
    - University with multiple campuses
    - Theater chain with multiple venues
    - Corporate campus with multiple buildings
    - Church network with multiple locations

    Each organization represents a separate customer/tenant in MSP scenarios.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Organization name (must be unique across system)",
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        db_index=True,
        help_text="URL-safe identifier for organization",
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Django site this organization belongs to (optional)",
    )

    # Status and features
    is_active = models.BooleanField(default=True, help_text="Whether organization is active")
    max_devices = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Device limit for this organization (null = unlimited)",
    )
    subscription_tier = models.CharField(
        max_length=50,
        default="basic",
        choices=[
            ("basic", "Basic"),
            ("pro", "Professional"),
            ("enterprise", "Enterprise"),
        ],
        help_text="Subscription/feature tier",
    )

    # Optional branding
    logo = models.ImageField(
        upload_to="org_logos/",
        null=True,
        blank=True,
        help_text="Organization logo for branded UI",
    )
    primary_color = models.CharField(
        max_length=7,
        default="#007bff",
        help_text="Primary brand color (hex format)",
    )

    # Metadata
    primary_contact = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_contact_for_orgs",
        help_text="Primary contact/admin for this organization",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model configuration for organizations."""

        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["site", "is_active"]),
        ]

    def __str__(self) -> str:
        """Return the organization name for admin listings."""
        return self.name

    def get_device_count(self) -> int:
        """Get total number of devices for this organization."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(location__building__site=self.site).count()

    def is_at_device_limit(self) -> bool:
        """Check if organization has reached device limit."""
        if self.max_devices is None:
            return False
        return self.get_device_count() >= self.max_devices


class Campus(models.Model):
    """Sub-organization unit for multi-campus deployments.

    Examples:
    - North Campus (University)
    - Downtown Theater (Theater Chain)
    - Building 5 (Corporate Campus)
    - Satellite Location (Church Network)

    Campuses provide an optional middle tier between Organization and Building.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="campuses",
        help_text="Parent organization",
    )
    name = models.CharField(max_length=200, help_text="Campus name")
    slug = models.SlugField(max_length=200, help_text="URL-safe identifier (unique within org)")

    # Location details
    address = models.TextField(blank=True, help_text="Physical address of campus")
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True, default="USA")
    timezone = models.CharField(max_length=50, default="UTC", help_text="IANA timezone identifier")

    # Status
    is_active = models.BooleanField(default=True, help_text="Whether campus is active")

    # Metadata
    notes = models.TextField(blank=True, help_text="Internal notes about campus")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model configuration for campuses."""

        verbose_name = "Campus"
        verbose_name_plural = "Campuses"
        unique_together = [["organization", "slug"]]
        ordering = ["organization", "name"]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self) -> str:
        """Return a display label combining organization and campus name."""
        return f"{self.organization.name} - {self.name}"


class OrganizationMembership(models.Model):
    """User membership in organizations with role-based permissions.

    Defines which organizations a user can access and their permission level
    within each organization.
    """

    ROLE_CHOICES = [
        ("viewer", "Viewer - Read-only access"),
        ("operator", "Operator - Can modify device assignments"),
        ("admin", "Admin - Full access except billing"),
        ("owner", "Owner - Full access including billing"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_memberships",
        help_text="User with access to organization",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text="Organization user has access to",
    )
    campus = models.ForeignKey(
        Campus,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="memberships",
        help_text="Optional: Limit user to specific campus only",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="viewer",
        help_text="User's permission level in organization",
    )
    is_active = models.BooleanField(default=True, help_text="Whether membership is active")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_memberships",
        help_text="User who created this membership",
    )

    class Meta:
        """Model configuration for membership records."""

        verbose_name = "Organization Membership"
        verbose_name_plural = "Organization Memberships"
        unique_together = [["user", "organization"]]
        ordering = ["organization", "user"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self) -> str:
        """Return a readable membership summary string."""
        campus_str = f" ({self.campus})" if self.campus else ""
        role_display = self.get_role_display()
        return f"{self.user.username} - {self.organization.name}{campus_str} [{role_display}]"

    def can_manage_users(self) -> bool:
        """Check if user can manage other users in organization."""
        return self.role in ["admin", "owner"]

    def can_manage_billing(self) -> bool:
        """Check if user can manage billing settings."""
        return self.role == "owner"

    def can_modify_devices(self) -> bool:
        """Check if user can modify device settings/assignments."""
        return self.role in ["operator", "admin", "owner"]
