"""A responding chassis reaches online through one lifecycle, from poll and realtime alike."""

from collections.abc import Callable

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager
from micboard.services.sync.chassis_ingest import ChassisIngestService, IngestMode
from micboard.services.sync.device_update_service import DeviceUpdateService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.fake_vendor import FakeVendorPlugin

pytestmark = pytest.mark.django_db

# Degraded and maintenance are operator-visible states a poll must not overwrite.
RESPONDING_OUTCOMES = [
    ("discovered", "online"),
    ("provisioning", "online"),
    ("offline", "online"),
    ("online", "online"),
    ("degraded", "degraded"),
    ("maintenance", "maintenance"),
]


def _poll_duplicate(chassis: WirelessChassis) -> None:
    ChassisIngestService.ingest(
        [
            NormalizedChassis(
                api_device_id=chassis.api_device_id,
                serial_number=chassis.serial_number,
                ip=str(chassis.ip),
            )
        ],
        manufacturer=chassis.manufacturer,
        mode=IngestMode.PARTIAL_EVENT,
    )


def _poll_moved(chassis: WirelessChassis) -> None:
    ChassisIngestService.ingest(
        [
            NormalizedChassis(
                api_device_id=chassis.api_device_id,
                serial_number=chassis.serial_number,
                ip="192.0.2.250",
            )
        ],
        manufacturer=chassis.manufacturer,
        mode=IngestMode.PARTIAL_EVENT,
    )


def _realtime(chassis: WirelessChassis) -> None:
    plugin = FakeVendorPlugin(
        [NormalizedChassis(api_device_id=chassis.api_device_id, ip=str(chassis.ip))]
    )
    DeviceUpdateService.update_models_from_api_data(
        api_data=plugin.raw_devices,
        manufacturer=chassis.manufacturer,
        plugin=plugin,
    )


@pytest.mark.parametrize("path", [_poll_duplicate, _poll_moved, _realtime])
@pytest.mark.parametrize(("start", "expected"), RESPONDING_OUTCOMES)
def test_every_path_applies_the_same_status_outcome(
    path: Callable[[WirelessChassis], None],
    start: str,
    expected: str,
) -> None:
    """Poll (duplicate and moved) and realtime agree on the status a response yields."""
    chassis = WirelessChassisFactory(
        manufacturer=ManufacturerFactory(code="responding-vendor"),
        status=start,
        ip="192.0.2.140",
    )

    path(chassis)

    chassis.refresh_from_db()
    assert chassis.status == expected
    assert chassis.is_online is (expected in {"online", "degraded"})
    if start in {"discovered", "provisioning", "offline"}:
        assert chassis.last_online_at is not None


@pytest.mark.parametrize(("start", "expected"), RESPONDING_OUTCOMES)
def test_lifecycle_reconciles_a_responding_chassis(start: str, expected: str) -> None:
    """The lifecycle owns the guard and the discovered -> provisioning -> online route."""
    chassis = WirelessChassisFactory(status=start)

    HardwareLifecycleManager().bring_responding_online(chassis, reason="test")

    chassis.refresh_from_db()
    assert chassis.status == expected


def test_lifecycle_refuses_to_revive_a_retired_chassis() -> None:
    """A retired chassis stays retired and the caller is told."""
    chassis = WirelessChassisFactory(status="retired")

    with pytest.raises(RuntimeError, match="Could not mark"):
        HardwareLifecycleManager().bring_responding_online(chassis, reason="test")

    chassis.refresh_from_db()
    assert chassis.status == "retired"


def test_guard_judges_the_locked_row_not_a_stale_offline_copy() -> None:
    """A copy that still says offline cannot pull a chassis out of maintenance."""
    chassis = WirelessChassisFactory(status="offline")
    WirelessChassis.objects.filter(pk=chassis.pk).update(status="maintenance")

    HardwareLifecycleManager().bring_responding_online(chassis, reason="test")

    chassis.refresh_from_db()
    assert chassis.status == "maintenance"


def test_stale_discovered_copy_of_an_online_row_is_left_online() -> None:
    """A stale discovered copy does not replay provisioning over an online row."""
    chassis = WirelessChassisFactory(status="discovered")
    WirelessChassis.objects.filter(pk=chassis.pk).update(status="online")

    HardwareLifecycleManager().bring_responding_online(chassis, reason="test")

    assert chassis.status == "online"
    assert WirelessChassis.objects.get(pk=chassis.pk).status == "online"
