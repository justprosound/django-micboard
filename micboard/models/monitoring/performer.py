"""Performer model for device users assigned to wireless units."""

from __future__ import annotations

from typing import ClassVar, cast

from django.db import models

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet


class PerformerQuerySet(TenantOptimizedQuerySet):
    """Query helpers for performers with tenant awareness."""

    def for_user(self, *, user) -> PerformerQuerySet:
        """Return performers managed by one of the user's active monitoring groups.

        In single-tenant mode, unassigned performers remain available so an
        operator can create their first assignment. MSP mode cannot safely
        expose a tenantless performer, so it only returns performers already
        linked through a tenant-scoped assignment.
        """
        tenant_scope = cast(PerformerQuerySet, super().for_user(user=user))
        if not user.is_authenticated:
            return tenant_scope
        if user.is_superuser:
            return tenant_scope

        from django.conf import settings

        from micboard.models.monitoring.performer_assignment import PerformerAssignment

        visible_assignments = PerformerAssignment.objects.for_user(user=user)
        visibility = models.Q(assignments__in=visible_assignments)
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            visibility |= models.Q(assignments__isnull=True)
        return tenant_scope.filter(visibility).distinct()

    def active(self) -> PerformerQuerySet:
        """Get all active performers."""
        return self.filter(is_active=True)

    def with_assignments(self) -> PerformerQuerySet:
        """Optimize: prefetch related assignments and units."""
        return self.prefetch_related("assignments", "assignments__wireless_unit")

    def by_monitoring_group(self, *, group) -> PerformerQuerySet:
        """Filter performers by monitoring group (through assignments)."""
        return self.filter(assignments__monitoring_group=group).distinct()


class PerformerManager(TenantOptimizedManager):
    """Manager with typed helpers for performers."""

    def get_queryset(self) -> PerformerQuerySet:
        return PerformerQuerySet(self.model, using=self._db)

    def active(self) -> PerformerQuerySet:
        return self.get_queryset().active()

    def for_user(self, *, user) -> PerformerQuerySet:
        """Return performers visible to the user."""
        return self.get_queryset().for_user(user=user)

    def with_assignments(self) -> PerformerQuerySet:
        return self.get_queryset().with_assignments()


class Performer(models.Model):
    """Represents a performer/talent with assigned wireless devices.

    Performers are device users (musicians, actors, speakers, etc.) who use
    WirelessUnits. They are separate from Users (technicians/admins) who
    monitor and manage the devices.
    """

    # Identity
    name = models.CharField(
        max_length=100,
        help_text="Performer name or stage name",
    )
    title = models.CharField(
        max_length=100,
        blank=True,
        help_text="Role or title (e.g., 'Lead Vocalist', 'News Anchor', 'Actor')",
    )
    role_description = models.TextField(
        blank=True,
        help_text="Description of performer's role and device requirements",
    )

    # Visual identification
    photo = models.ImageField(
        upload_to="performer_photos/",
        null=True,
        blank=True,
        help_text="Headshot or identification photo for dashboards",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this performer is currently active",
    )

    # Contact info (optional)
    email = models.EmailField(
        blank=True,
        help_text="Contact email for the performer",
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Contact phone number",
    )

    # Metadata
    notes = models.TextField(
        blank=True,
        help_text="Notes about the performer (equipment preferences, special requirements)",
    )

    # Tracking
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this performer was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp",
    )

    objects = PerformerManager()

    class Meta:
        verbose_name = "Performer"
        verbose_name_plural = "Performers"
        ordering: ClassVar[list[str]] = ["name"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        role = f" ({self.title})" if self.title else ""
        return f"{self.name}{role}"

    def get_assigned_units(self):
        """Get all wireless units assigned to this performer."""
        from micboard.models.hardware.wireless_unit import WirelessUnit

        return WirelessUnit.objects.filter(
            performer_assignments__performer=self,
            status__in=["online", "degraded", "provisioning"],
        )

    def get_monitoring_groups(self):
        """Get all monitoring groups that manage this performer."""
        return self.assignments.values_list("monitoring_group", flat=True).distinct()
