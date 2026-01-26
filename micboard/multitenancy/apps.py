"""App configuration for multitenancy module."""

from __future__ import annotations

from django.apps import AppConfig


class MultitenancyConfig(AppConfig):
    """Configuration for optional multitenancy module."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "micboard.multitenancy"
    label = "micboard_multitenancy"
    verbose_name = "Micboard Multi-Tenancy (MSP)"
