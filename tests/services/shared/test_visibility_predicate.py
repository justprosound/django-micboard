"""The one predicate for "rows this user may see".

Visibility is asked in four places — views, admin, services, and tasks — about models that
carry their own tenant-aware manager and models that do not. `visible_to` owns that dispatch,
so no caller has to know which kind of model it holds.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Building
from micboard.models.settings.registry import Setting
from micboard.services.shared.access_policy import visible_to

pytestmark = pytest.mark.django_db

ANONYMOUS = SimpleNamespace(is_authenticated=False, is_superuser=False)


def test_a_model_with_its_own_visibility_override_is_asked_through_it() -> None:
    """A model that narrows visibility itself keeps its own queryset type and rule."""
    from micboard.models.rf_coordination.rf_channel import (
        RFChannel,
        RFChannelQuerySet,
    )

    result = visible_to(RFChannel, user=ANONYMOUS)

    assert isinstance(result, RFChannelQuerySet)
    assert result.query.is_empty()


def test_a_model_without_a_tenant_manager_falls_back_to_the_shared_cascade() -> None:
    """Visibility still resolves for a model whose manager is the Django default."""
    result = visible_to(Building, user=ANONYMOUS)

    assert result.query.is_empty()


def test_every_model_fails_closed_for_an_unauthenticated_caller() -> None:
    """One predicate means one place where an anonymous request is refused."""
    for model in (WirelessChassis, Building, Setting):
        assert visible_to(model, user=ANONYMOUS).query.is_empty()


def test_the_predicate_honours_the_database_it_is_asked_about() -> None:
    """A caller working on a specific alias gets a queryset bound to that alias."""
    assert visible_to(Building, user=ANONYMOUS, using="default").db == "default"
