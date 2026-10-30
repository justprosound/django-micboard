"""Isolation fixtures for sync service tests."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.common.base import plugin as plugin_module
from tests.factories.base import UserFactory
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.factories.monitoring import PerformerAssignmentFactory


@pytest.fixture(autouse=True)
def isolate_hardware_factory_side_effects(
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep model factories local while preserving their database behavior."""
    settings.TESTING = True
    monkeypatch.setattr(
        plugin_module,
        "build_manufacturer_plugin",
        lambda _manufacturer: (_ for _ in ()).throw(ModuleNotFoundError("no integration")),
    )
    yield


def _watched_chassis(*, last_seen: datetime, last_online_at: datetime) -> SimpleNamespace:
    """An online chassis whose online unit is watched by a user who wants offline alerts."""
    manufacturer = ManufacturerFactory(code="vendor")
    present = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="present",
        serial_number="present-1",
        ip="192.0.2.10",
        status="online",
    )
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="dropped",
        serial_number="dropped-1",
        ip="192.0.2.11",
        status="online",
        max_channels=1,
    )
    WirelessChassis.objects.filter(pk=chassis.pk).update(
        last_seen=last_seen, last_online_at=last_online_at
    )
    unit = WirelessUnitFactory(
        base_chassis=chassis,
        manufacturer=manufacturer,
        assigned_resource=chassis.rf_channels.get(channel_number=1),
        slot=1,
        status="online",
    )
    assignment = PerformerAssignmentFactory(wireless_unit=unit, alert_on_hardware_offline=True)
    user = UserFactory()
    assignment.monitoring_group.users.add(user)
    return SimpleNamespace(
        manufacturer=manufacturer, present=present, chassis=chassis, unit=unit, user=user
    )


@pytest.fixture
def watched(no_email: Mock) -> SimpleNamespace:
    """The chassis last seen and last online at known times."""
    now = timezone.now()
    return _watched_chassis(
        last_seen=now - timedelta(minutes=3), last_online_at=now - timedelta(days=2)
    )


@pytest.fixture
def no_email() -> Iterator[Mock]:
    """Alert delivery sends mail; these tests assert on the persisted alert."""
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification"
    ) as send:
        yield send
