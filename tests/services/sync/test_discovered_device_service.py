"""Discovered-device lifecycle policy contracts."""

from __future__ import annotations

import pytest

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.core.device_metadata import ShureMetadataAccessor
from micboard.services.sync.discovered_device_service import (
    can_promote_device_to_chassis,
    get_device_communication_protocol,
    get_device_incompatibility_reason,
    get_device_metadata_accessor,
    is_device_manageable,
)
from tests.factories.discovery import DiscoveredDeviceFactory, ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_metadata_accessor_uses_discovered_manufacturer_and_payload() -> None:
    """Lifecycle policy delegates vendor metadata interpretation to its strategy."""
    device = DiscoveredDeviceFactory.build(
        manufacturer=ManufacturerFactory.build(code="shure"),
        metadata={"deviceState": "ONLINE"},
    )

    accessor = get_device_metadata_accessor(device)

    assert isinstance(accessor, ShureMetadataAccessor)
    assert accessor.get_device_state() == "ONLINE"


@pytest.mark.parametrize(
    ("status", "device_id", "expected"),
    [
        (DiscoveredDevice.STATUS_READY, "device-1", True),
        (DiscoveredDevice.STATUS_READY, "", False),
        (DiscoveredDevice.STATUS_PENDING, "device-1", False),
    ],
)
def test_manageable_requires_ready_state_and_external_identity(
    status: str,
    device_id: str,
    expected: bool,
) -> None:
    """API management begins only after discovery readiness and identity are known."""
    device = DiscoveredDeviceFactory.build(status=status, api_device_id=device_id)

    assert is_device_manageable(device) is expected


@pytest.mark.parametrize(
    ("status", "api_device_id", "metadata", "expected"),
    [
        (
            DiscoveredDevice.STATUS_INCOMPATIBLE,
            "device-1",
            {"incompatibility_reason": "Unsupported firmware"},
            "Unsupported firmware",
        ),
        (
            DiscoveredDevice.STATUS_INCOMPATIBLE,
            "device-1",
            {},
            "Device is incompatible with current API version.",
        ),
        (
            DiscoveredDevice.STATUS_PENDING,
            "device-1",
            {"state": "DISCOVERED"},
            "Device is in DISCOVERED state",
        ),
        (
            DiscoveredDevice.STATUS_PENDING,
            "device-1",
            {"state": "CONNECTING"},
            "Device discovered but not yet ready for management.",
        ),
        (
            DiscoveredDevice.STATUS_ERROR,
            "device-1",
            {},
            "Device is in ERROR state.",
        ),
        (
            DiscoveredDevice.STATUS_OFFLINE,
            "device-1",
            {},
            "Device is offline.",
        ),
        (
            DiscoveredDevice.STATUS_READY,
            "",
            {},
            "Device ID not available from API.",
        ),
        (DiscoveredDevice.STATUS_READY, "device-1", {}, None),
    ],
)
def test_incompatibility_reason_explains_each_lifecycle_blocker(
    status: str,
    api_device_id: str,
    metadata: dict[str, str],
    expected: str | None,
) -> None:
    """Every non-manageable state has an operator-facing explanation."""
    device = DiscoveredDeviceFactory.build(
        status=status,
        api_device_id=api_device_id,
        metadata=metadata,
    )

    reason = get_device_incompatibility_reason(device)

    if expected is None:
        assert reason is None
    else:
        assert expected in reason


def test_promotion_rejects_an_existing_managed_chassis() -> None:
    """Discovery cannot create a second chassis for an already managed address."""
    chassis = WirelessChassisFactory(ip="192.0.2.140")
    device = DiscoveredDeviceFactory(
        ip=chassis.ip,
        manufacturer=chassis.manufacturer,
        status=DiscoveredDevice.STATUS_READY,
        api_device_id="device-140",
    )

    assert can_promote_device_to_chassis(device) == (
        False,
        "Device is already managed as WirelessChassis",
    )


def test_promotion_rejects_lifecycle_incompatibility() -> None:
    """Lifecycle blockers are retained when evaluating promotion eligibility."""
    device = DiscoveredDeviceFactory(
        status=DiscoveredDevice.STATUS_OFFLINE,
        api_device_id="device-141",
    )

    assert can_promote_device_to_chassis(device) == (
        False,
        "Device is offline. Check power and network connectivity.",
    )


def test_promotion_requires_manufacturer_after_lifecycle_validation() -> None:
    """Ready anonymous discoveries cannot select a normalization plugin."""
    device = DiscoveredDeviceFactory(
        manufacturer=None,
        status=DiscoveredDevice.STATUS_READY,
        api_device_id="device-142",
    )

    assert can_promote_device_to_chassis(device) == (False, "No manufacturer specified")


def test_ready_identified_device_can_be_promoted() -> None:
    """A unique ready discovery with a manufacturer is eligible for promotion."""
    device = DiscoveredDeviceFactory(
        status=DiscoveredDevice.STATUS_READY,
        api_device_id="device-143",
    )

    assert can_promote_device_to_chassis(device) == (
        True,
        "Device is ready to be promoted to managed chassis",
    )


def test_communication_protocol_is_optional_vendor_metadata() -> None:
    """Vendor protocol metadata is returned when supported and absent otherwise."""
    shure = DiscoveredDeviceFactory.build(
        manufacturer=ManufacturerFactory.build(code="shure"),
        metadata={"communicationProtocol": {"name": "Shure Link"}},
    )
    generic = DiscoveredDeviceFactory.build(
        manufacturer=ManufacturerFactory.build(code="generic"),
        metadata={},
    )

    assert get_device_communication_protocol(shure) == "Shure Link"
    assert get_device_communication_protocol(generic) is None
