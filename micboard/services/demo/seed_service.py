"""Load the demonstration dataset and refresh the parts a fixture cannot express.

The hardware, locations, and assignments live in the ``demo`` fixture, which Django loads
with ``raw=True``. Every hook in :mod:`micboard.model_lifecycle` returns early on a raw
save, so loading the fixture never resolves a manufacturer integration and never needs the
live API credentials a real device save would demand.

Two things cannot live in a fixture: telemetry has to be dated relative to now, or the demo
reads as months stale, and the read-only account's password has to come from the
environment rather than a committed hash.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, ClassVar

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from micboard.services.demo.dtos import DemoSeedSummary

DEMO_FIXTURE = "demo"
DEMO_CHASSIS_API_ID = "demo-ulxd4q-001"
DEMO_GROUP_NAME = "Demo (read-only)"
DEMO_USERNAME = "demo"


class DemoSeedService:
    """Load the demo fixture, give it fresh telemetry, and manage the read-only account."""

    # Minutes before now at which to write a sample, newest last.
    SAMPLE_OFFSETS_MINUTES: ClassVar[tuple[int, ...]] = (90, 60, 30, 0)

    @transaction.atomic
    def seed(self, *, read_only_password: str | None = None) -> DemoSeedSummary:
        """Load the fixture and return what the run produced.

        Safe to run on every deployment start: the fixture upserts on its committed primary
        keys, and the telemetry window is rewritten rather than appended to.
        """
        call_command("loaddata", DEMO_FIXTURE, verbosity=0)
        units = list(self._demo_units())
        samples = self._refresh_telemetry(units)
        created = False
        if read_only_password:
            created = self._apply_read_only_account(password=read_only_password)
        return DemoSeedSummary(
            units=len(units),
            telemetry_samples=samples,
            read_only_user_created=created,
        )

    def _demo_units(self) -> Any:
        """Return the transmitters belonging to the demo chassis."""
        unit_model = apps.get_model("micboard", "WirelessUnit")
        return unit_model.objects.filter(base_chassis__api_device_id=DEMO_CHASSIS_API_ID)

    def _refresh_telemetry(self, units: list[Any]) -> int:
        """Replace each demo transmitter's telemetry with a window ending now."""
        session_model = apps.get_model("micboard", "WirelessUnitSession")
        sample_model = apps.get_model("micboard", "WirelessUnitSample")
        now = timezone.now()
        written = 0

        for unit in units:
            # Rewriting beats appending: repeated deployments would otherwise accumulate
            # a sample every restart, and the oldest ones would drift out of every view.
            sample_model.objects.filter(session__wireless_unit=unit).delete()
            session_model.objects.filter(wireless_unit=unit).delete()

            session = session_model.objects.create(
                wireless_unit=unit,
                started_at=now - timedelta(minutes=max(self.SAMPLE_OFFSETS_MINUTES)),
                last_seen=now,
                is_active=True,
                last_status=unit.status,
            )
            for offset in self.SAMPLE_OFFSETS_MINUTES:
                sample_model.objects.create(
                    session=session,
                    timestamp=now - timedelta(minutes=offset),
                    # Batteries drain across the window towards the level the fixture
                    # records, so the battery-history view shows a downward trend.
                    battery=min(100, (unit.battery or 0) + offset // 15),
                    audio_level=unit.assigned_resource.audio_level
                    if unit.assigned_resource
                    else None,
                    rf_level=(
                        unit.assigned_resource.rf_signal_strength
                        if unit.assigned_resource
                        else None
                    ),
                    status=unit.status,
                    frequency=(unit.assigned_resource.frequency if unit.assigned_resource else ""),
                )
                written += 1
        return written

    def _apply_read_only_account(self, *, password: str) -> bool:
        """Create or reset a staff account that can open the admin and change nothing."""
        group, _ = Group.objects.get_or_create(name=DEMO_GROUP_NAME)
        group.permissions.set(
            Permission.objects.filter(
                content_type__app_label__in=("micboard", "micboard_multitenancy"),
                codename__startswith="view_",
            )
        )

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={"is_staff": True, "is_superuser": False},
        )
        # Reapplied on every run so a rotated password takes effect, and so an account that
        # somehow gained privileges cannot keep them across a redeploy.
        user.is_staff = True
        user.is_superuser = False
        user.set_password(password)
        user.save(update_fields=["is_staff", "is_superuser", "password"])
        user.groups.set([group])
        user.user_permissions.clear()
        return created
