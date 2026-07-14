"""Contract tests for the project model-factory catalog."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from django.apps import apps
from django.db import models
from django.test import override_settings

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from tests.factories.hardware import ChargerSlotFactory, WirelessUnitFactory
from tests.factories.locations import BuildingFactory, LocationFactory, RoomFactory
from tests.factories.multitenancy import (
    CampusFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
)
from tests.factories.registry import factory_for, iter_factory_specs
from tests.factories.rf_coordination import RegulatoryDomainFactory


def _installed_project_app_labels() -> frozenset[str]:
    """Return app labels owned by the installed django-micboard package."""
    return frozenset(
        config.label
        for config in apps.get_app_configs()
        if config.name == "micboard" or config.name.startswith("micboard.")
    )


def _installed_project_models() -> tuple[type[models.Model], ...]:
    """Return the managed concrete models owned by installed project apps."""
    return tuple(
        sorted(
            (
                model
                for model in apps.get_models()
                if model._meta.app_label in _installed_project_app_labels()
                and model._meta.managed
                and not model._meta.abstract
                and not model._meta.proxy
                and not model._meta.auto_created
                and not model._meta.swapped
            ),
            key=lambda model: model._meta.label_lower,
        )
    )


@contextmanager
def _without_external_lifecycle_effects() -> Iterator[None]:
    """Keep factory smoke tests inside local database seams."""
    with (
        patch(
            "micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin",
            return_value=None,
        ),
        patch("micboard.services.sync.discovery_trigger_service.trigger_discovery"),
    ):
        yield


def test_factory_registry_matches_installed_project_models() -> None:
    """Every installed concrete project model has exactly one factory."""
    expected_labels = {model._meta.label_lower for model in _installed_project_models()}
    registered_labels = [spec.label.lower() for spec in iter_factory_specs()]

    assert registered_labels == sorted(registered_labels)
    assert set(registered_labels) == expected_labels


def test_factory_lookup_accepts_model_classes_instances_and_labels() -> None:
    """Callers can use whichever model representation they already have."""
    expected = factory_for(Manufacturer)

    assert factory_for(Manufacturer()) is expected
    assert factory_for("MICBOARD.MANUFACTURER") is expected


def test_factory_lookup_rejects_unregistered_labels() -> None:
    """Missing adapters fail with a focused lookup error."""
    with pytest.raises(LookupError, match=r"No factory registered for missing\.model"):
        factory_for("missing.Model")


@pytest.mark.django_db
@override_settings(TESTING=True)
def test_capacity_scoped_factories_stay_within_fresh_parent_limits() -> None:
    """Default child positions remain valid as global factory sequences advance."""
    with _without_external_lifecycle_effects():
        slots = [ChargerSlotFactory() for _ in range(6)]
        units = [WirelessUnitFactory() for _ in range(6)]

    assert all(slot.slot_number <= slot.charger.slot_count for slot in slots)
    assert all(unit.slot <= unit.base_chassis.max_channels for unit in units)


@pytest.mark.django_db
def test_factories_derive_parents_from_explicit_children() -> None:
    """Existing child objects keep generated relationship graphs consistent."""
    room = RoomFactory()
    campus = CampusFactory()

    location = LocationFactory(room=room)
    membership = OrganizationMembershipFactory(campus=campus)

    assert location.building == room.building
    assert membership.organization == campus.organization


@pytest.mark.django_db
def test_factories_reject_explicitly_inconsistent_relationships() -> None:
    """Conflicting parent and child overrides fail before invalid data is saved."""
    room = RoomFactory()
    campus = CampusFactory()

    with pytest.raises(ValueError, match="Location room must belong to its building"):
        LocationFactory(room=room, building=BuildingFactory())
    with pytest.raises(ValueError, match="Membership campus must belong to its organization"):
        OrganizationMembershipFactory(campus=campus, organization=OrganizationFactory())


@pytest.mark.django_db
def test_building_factory_ignores_ambient_regulatory_domains() -> None:
    """Building defaults select their own explicit regulatory domain."""
    ambient_domain = RegulatoryDomainFactory(country_code="ZZ")

    building = BuildingFactory()

    assert building.regulatory_domain != ambient_domain
    assert building.regulatory_domain.country_code == building.country


@pytest.mark.django_db
@override_settings(TESTING=True)
@pytest.mark.parametrize(
    "model",
    _installed_project_models(),
    ids=lambda model: model._meta.label,
)
def test_factory_creates_two_valid_persisted_instances(model: type[models.Model]) -> None:
    """Factory defaults satisfy relations, validation, and uniqueness."""
    with _without_external_lifecycle_effects():
        factory_class = factory_for(model)
        first = factory_class.create()
        second = factory_class.create()

    assert type(first) is model
    assert type(second) is model
    assert first.pk is not None
    assert second.pk is not None
    assert first.pk != second.pk
    first.full_clean()
    second.full_clean()


@pytest.mark.parametrize(
    ("settings_module", "script"),
    [
        (
            "tests.core_only_settings",
            (
                "from django.apps import apps; "
                "from tests.factories.registry import iter_factory_specs; "
                "labels = {config.label for config in apps.get_app_configs() "
                "if config.name == 'micboard' or config.name.startswith('micboard.')}; "
                "expected = {model._meta.label for model in apps.get_models() "
                "if model._meta.app_label in labels and model._meta.managed "
                "and not model._meta.abstract and not model._meta.proxy "
                "and not model._meta.auto_created and not model._meta.swapped}; "
                "factory_labels = {spec.label for spec in iter_factory_specs()}; "
                "assert factory_labels == expected"
            ),
        ),
        (
            "tests.custom_user_settings",
            (
                "from tests.factories.registry import factory_for; "
                "profile = factory_for('micboard.UserProfile').build(); "
                "assert profile.user._meta.label == 'custom_user_app.CustomUser'"
            ),
        ),
    ],
)
def test_factory_registry_supports_host_profiles(settings_module: str, script: str) -> None:
    """Optional-app and swappable-user hosts import the factory catalog safely."""
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": settings_module}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", f"import django; django.setup(); {script}"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
