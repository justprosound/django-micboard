"""Service-level tests for performer records and assignments."""

from __future__ import annotations

import pytest

from micboard.services.core.performer import PerformerService
from tests.factories.monitoring import (
    MonitoringGroupFactory,
    PerformerAssignmentFactory,
    PerformerFactory,
)


@pytest.mark.django_db
def test_get_active_performers_filters_and_orders_by_name() -> None:
    """Return only active performers in deterministic display order."""
    zulu = PerformerFactory(name="Zulu", is_active=True)
    alpha = PerformerFactory(name="Alpha", is_active=True)
    PerformerFactory(name="Inactive", is_active=False)

    assert list(PerformerService.get_active_performers()) == [alpha, zulu]


@pytest.mark.parametrize(
    ("query", "field", "value"),
    [
        ("nightingale", "name", "The Nightingale"),
        ("vocalist", "title", "Lead Vocalist"),
        ("artist.example", "email", "contact@artist.example"),
        ("555-0100", "phone", "+1-555-0100"),
    ],
)
@pytest.mark.django_db
def test_search_performers_matches_each_supported_contact_field(
    query: str,
    field: str,
    value: str,
) -> None:
    """Search identity, role, and both contact channels case-insensitively."""
    target = PerformerFactory(**{field: value})
    PerformerFactory(name="Unrelated")

    assert list(PerformerService.search_performers(query=query)) == [target]


@pytest.mark.django_db
def test_create_performer_persists_full_public_contract() -> None:
    """Persist supplied contact and role data with an active default."""
    performer = PerformerService.create_performer(
        name="Ada Artist",
        title="Presenter",
        email="ada@example.test",
        phone="555-0101",
        role_description="Keynote presenter",
        notes="Uses a handheld transmitter",
    )

    performer.refresh_from_db()
    assert performer.name == "Ada Artist"
    assert performer.title == "Presenter"
    assert performer.email == "ada@example.test"
    assert performer.phone == "555-0101"
    assert performer.role_description == "Keynote presenter"
    assert performer.notes == "Uses a handheld transmitter"
    assert performer.is_active is True


@pytest.mark.django_db
def test_update_performer_applies_explicit_values_including_empty_and_false() -> None:
    """Distinguish explicit falsey updates from omitted fields."""
    performer = PerformerFactory(
        name="Original",
        title="Singer",
        email="original@example.test",
        phone="555-0110",
        role_description="Original role",
        notes="Original notes",
        is_active=True,
    )

    returned = PerformerService.update_performer(
        performer,
        name="Updated",
        title="",
        email="updated@example.test",
        phone="",
        role_description="Updated role",
        notes="",
        is_active=False,
    )

    assert returned is performer
    performer.refresh_from_db()
    assert performer.name == "Updated"
    assert performer.title == ""
    assert performer.email == "updated@example.test"
    assert performer.phone == ""
    assert performer.role_description == "Updated role"
    assert performer.notes == ""
    assert performer.is_active is False


@pytest.mark.django_db
def test_deactivate_performer_soft_deletes_record() -> None:
    """Deactivate without deleting performer identity or history."""
    performer = PerformerFactory(is_active=True)

    PerformerService.deactivate_performer(performer)

    performer.refresh_from_db()
    assert performer.is_active is False


@pytest.mark.django_db
def test_assignment_query_eager_loads_unit_and_group(django_assert_num_queries) -> None:
    """Return assignment relations without per-row follow-up queries."""
    performer = PerformerFactory()
    assignment = PerformerAssignmentFactory(performer=performer)

    with django_assert_num_queries(1):
        assignments = list(PerformerService.get_performer_assignments(performer))
        related_values = [
            (item.wireless_unit.name, item.monitoring_group.name) for item in assignments
        ]

    assert assignments == [assignment]
    assert related_values == [(assignment.wireless_unit.name, assignment.monitoring_group.name)]


@pytest.mark.django_db
def test_monitoring_groups_are_distinct_across_multiple_assignments() -> None:
    """Return each managing group once even when it owns multiple assignments."""
    performer = PerformerFactory()
    group = MonitoringGroupFactory()
    PerformerAssignmentFactory(performer=performer, monitoring_group=group)
    PerformerAssignmentFactory(performer=performer, monitoring_group=group)

    assert list(PerformerService.get_monitoring_groups_for_performer(performer)) == [group]


@pytest.mark.django_db
def test_performer_details_aggregate_relations_and_counts() -> None:
    """Assemble performer identity, relation querysets, and summary counts."""
    performer = PerformerFactory(is_active=True)
    first_group = MonitoringGroupFactory()
    second_group = MonitoringGroupFactory()
    assignments = [
        PerformerAssignmentFactory(performer=performer, monitoring_group=first_group),
        PerformerAssignmentFactory(performer=performer, monitoring_group=second_group),
    ]

    details = PerformerService.get_performer_details(performer)

    assert details["performer"] == performer
    assert list(details["assignments"]) == assignments
    assert details["assignment_count"] == 2
    assert set(details["monitoring_groups"]) == {first_group, second_group}
    assert details["group_count"] == 2
    assert details["is_active"] is True
    assert details["last_updated"] == performer.updated_at
