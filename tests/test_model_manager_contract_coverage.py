"""Tenant filter contracts on the model querysets.

Which rows a user may see is answered by `micboard.services.shared.visibility`; these cover
the membership filter it composes, which has to fail closed on its own.
"""

from __future__ import annotations

from django.test import override_settings

from micboard.models.base_managers import TenantOptimizedQuerySet
from micboard.models.settings.registry import Setting


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_membership_scope_fails_closed_without_an_ownership_path() -> None:
    """A model with no declared tenant ownership cannot be scoped by membership."""
    setting_queryset = TenantOptimizedQuerySet(Setting, using="default")

    assert setting_queryset.for_memberships([(1, 2)]).query.is_empty()
    assert setting_queryset.for_memberships([]).query.is_empty()
