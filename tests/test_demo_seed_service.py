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
from django.core.management import call_command
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


def test_seeding_refuses_a_database_that_holds_other_hardware() -> None:
    """The fixture carries explicit primary keys, so it must never land on real records."""
    chassis_model = apps.get_model("micboard", "WirelessChassis")
    manufacturer_model = apps.get_model("micboard", "Manufacturer")
    manufacturer = manufacturer_model.objects.create(name="Real Vendor", code="shure")
    chassis_model.objects.create(
        manufacturer=manufacturer,
        api_device_id="production-receiver-1",
        role="receiver",
        ip="192.0.2.10",
    )

    with pytest.raises(ValueError, match="refusing to seed"):
        DemoSeedService().seed()


def test_dropping_the_password_retires_the_existing_account() -> None:
    """Removing the environment variable must not leave a known staff login usable."""
    DemoSeedService().seed(read_only_password="first-password")

    DemoSeedService().seed()

    user = get_user_model().objects.get(username=DEMO_USERNAME)
    assert user.is_active is False
    assert user.is_staff is False
    assert not user.check_password("first-password")
    assert not user.has_usable_password()


def test_reseeding_reactivates_a_retired_account() -> None:
    """A redeploy that restores the password must restore the ability to sign in."""
    DemoSeedService().seed(read_only_password="first-password")
    DemoSeedService().seed()

    DemoSeedService().seed(read_only_password="second-password")

    user = get_user_model().objects.get(username=DEMO_USERNAME)
    assert user.is_active is True
    assert user.is_staff is True
    assert user.check_password("second-password")


def test_the_command_reports_what_it_seeded(capsys: pytest.CaptureFixture[str]) -> None:
    """The management command is the deployment's entry point, so it must run clean."""
    call_command("seed_demo_data")

    output = capsys.readouterr().out
    assert "Loaded the demo fixture" in output
    assert "the 'demo' account was not created" in output


def test_the_command_creates_then_resets_the_account(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Deployments pass the password through the environment on every start."""
    call_command("seed_demo_data", read_only_password="from-the-environment")
    assert "Created the read-only 'demo' account" in capsys.readouterr().out

    call_command("seed_demo_data", read_only_password="rotated")

    assert "Reset the password" in capsys.readouterr().out
    assert get_user_model().objects.get(username=DEMO_USERNAME).check_password("rotated")
