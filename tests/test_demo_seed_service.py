"""Contract tests for the demonstration dataset seeder.

The seeder runs on every start of the public demo deployment, so the two properties that
matter are that it produces a coherent dataset and that running it again is a no-op. The
read-only account is security-relevant: it must be able to open the admin and change
nothing.
"""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.utils import timezone

import pytest

from micboard.services.demo.seed_service import (
    DEMO_CHASSIS_API_ID,
    DEMO_GROUP_NAME,
    DEMO_USERNAME,
    DemoSeedService,
)

pytestmark = pytest.mark.django_db


def test_loading_the_fixture_produces_a_coherent_dataset() -> None:
    """Every dashboard surface needs records: hardware, channels, assignments, telemetry."""
    summary = DemoSeedService().seed()

    assert summary.units > 0
    assert summary.telemetry_samples == summary.units * len(DemoSeedService.SAMPLE_OFFSETS_MINUTES)

    chassis_model = apps.get_model("micboard", "WirelessChassis")
    channel_model = apps.get_model("micboard", "RFChannel")
    assert chassis_model.objects.filter(api_device_id=DEMO_CHASSIS_API_ID).exists()
    assert channel_model.objects.count() == summary.units


def test_every_unit_is_wired_to_a_channel_and_an_assignment() -> None:
    """A transmitter with no channel or performer would render as an orphan row."""
    DemoSeedService().seed()

    unit_model = apps.get_model("micboard", "WirelessUnit")
    assignment_model = apps.get_model("micboard", "PerformerAssignment")
    for unit in unit_model.objects.all():
        assert unit.assigned_resource is not None
        assert unit.base_chassis is not None
        assert assignment_model.objects.filter(wireless_unit=unit).exists()


def test_seeding_twice_leaves_the_record_counts_unchanged() -> None:
    """The deployment reseeds on every container start, so the run must be idempotent."""
    DemoSeedService().seed()
    sample_model = apps.get_model("micboard", "WirelessUnitSample")
    unit_model = apps.get_model("micboard", "WirelessUnit")
    first_samples = sample_model.objects.count()
    first_units = unit_model.objects.count()

    DemoSeedService().seed()

    assert sample_model.objects.count() == first_samples
    assert unit_model.objects.count() == first_units


def test_telemetry_is_dated_relative_to_now() -> None:
    """Frozen fixture timestamps would make the demo read as months stale."""
    DemoSeedService().seed()

    sample_model = apps.get_model("micboard", "WirelessUnitSample")
    newest = sample_model.objects.order_by("-timestamp").first()
    assert newest is not None
    assert timezone.now() - newest.timestamp < timedelta(minutes=5)


def test_the_demo_account_is_not_created_without_a_password() -> None:
    """A published demo must never get a staff login with a guessable default."""
    summary = DemoSeedService().seed()

    assert summary.read_only_user_created is False
    assert not get_user_model().objects.filter(username=DEMO_USERNAME).exists()


def test_the_demo_account_can_view_but_not_change_anything() -> None:
    """Read-only is the whole security model of the public demo."""
    DemoSeedService().seed(read_only_password="not-a-real-password")

    user = get_user_model().objects.get(username=DEMO_USERNAME)
    assert user.is_staff is True
    assert user.is_superuser is False
    assert user.check_password("not-a-real-password")

    codenames = {permission.codename for permission in user.groups.get().permissions.all()}
    assert codenames, "the demo group must carry the view permissions"
    assert all(codename.startswith("view_") for codename in codenames)
    assert not user.user_permissions.exists()


def test_reseeding_rotates_the_demo_password_and_keeps_it_unprivileged() -> None:
    """Redeploying with a new password must take effect and must not escalate the account."""
    DemoSeedService().seed(read_only_password="first-password")
    user = get_user_model().objects.get(username=DEMO_USERNAME)
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])

    DemoSeedService().seed(read_only_password="second-password")

    user.refresh_from_db()
    assert user.check_password("second-password")
    assert user.is_superuser is False
    assert user.groups.get().name == DEMO_GROUP_NAME
