"""Which database `visible_to` reads a tenant boundary from.

`visible_to(model, user=..., using=alias)` answers "rows this user may see" against one
named database. In MSP mode answering it takes two reads, not one: the caller's active
organization memberships are read and materialised first, and only then are the model's rows
narrowed to them. The alias therefore has to govern the queryset *before* the tenant boundary
is applied, not only after — otherwise a multi-database host narrows one database's rows by
another database's memberships.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.db import router

import pytest

from micboard.models.base_managers import TenantOptimizedQuerySet
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.monitoring.performer import Performer
from micboard.services.shared.access_policy import visible_to

# An unauthenticated caller makes `for_user` return an empty queryset without reading
# anything, so these tests observe routing without touching a database.
ANONYMOUS = SimpleNamespace(is_authenticated=False, is_superuser=False, pk=None)


def _database_seen_by_for_user(
    model: type[Any],
    *,
    using: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> str | None:
    """Return the database bound to the queryset `for_user` was applied to."""
    observed: list[str | None] = []
    original = TenantOptimizedQuerySet.for_user

    def record_database(self: Any, *, user: Any) -> Any:
        observed.append(self.db)
        return original(self, user=user)

    monkeypatch.setattr(TenantOptimizedQuerySet, "for_user", record_database)
    visible_to(model, user=ANONYMOUS, using=using)
    assert len(observed) == 1, "for_user must be applied exactly once"
    return observed[0]


def test_the_tenant_boundary_is_applied_on_the_database_the_caller_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Applying the alias to the finished queryset is too late.

    `for_user` materialises the caller's memberships as it builds, so a queryset that is
    only retargeted afterwards has already read that boundary from the wrong database.
    """
    assert (
        _database_seen_by_for_user(WirelessChassis, using="replica", monkeypatch=monkeypatch)
        == "replica"
    )


def test_a_model_on_the_shared_cascade_is_routed_the_same_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both branches of the dispatch answer the same question, so both honour the alias."""
    assert (
        _database_seen_by_for_user(Performer, using="replica", monkeypatch=monkeypatch) == "replica"
    )


def test_an_unnamed_database_falls_back_to_the_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Callers that name no database keep getting the router's read choice."""
    expected = router.db_for_read(WirelessChassis)

    assert (
        _database_seen_by_for_user(WirelessChassis, using=None, monkeypatch=monkeypatch) == expected
    )


def test_the_returned_queryset_targets_the_named_database() -> None:
    """Routing the intermediate read must not stop routing the final one."""
    assert visible_to(WirelessChassis, user=ANONYMOUS, using="replica").db == "replica"
