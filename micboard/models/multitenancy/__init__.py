"""Multi-tenancy support models (placeholder).

Note: This module provides placeholder Organization and Site models for multi-tenant scenarios.
In production, consider using django-organizations or django-tenants for full multi-tenancy support.
"""

from __future__ import annotations

from django.db import models


class Organization(models.Model):
    """Organization model for multi-tenant deployments."""

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self) -> str:
        return self.name


class Site(models.Model):
    """Site model representing a location or venue within an organization."""

    name = models.CharField(max_length=200)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="sites")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Site"
        verbose_name_plural = "Sites"
        unique_together = [("organization", "name")]

    def __str__(self) -> str:
        return f"{self.organization.name} - {self.name}"


__all__ = [
    "Organization",
    "Site",
]
