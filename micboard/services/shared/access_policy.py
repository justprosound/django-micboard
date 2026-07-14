"""Shared predicates for tenant-wide access decisions."""

from __future__ import annotations

from typing import Any

from django.conf import settings


def has_unrestricted_tenant_access(user: Any) -> bool:
    """Return whether ``user`` may bypass organization membership boundaries."""
    return bool(
        getattr(user, "is_superuser", False)
        and getattr(settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True)
    )
