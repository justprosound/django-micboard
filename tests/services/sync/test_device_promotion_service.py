"""Discovered-device promotion orchestration contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.services.core.hardware import NormalizedChassis
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.sync.device_promotion_service import DevicePromotionService
from tests.factories.discovery import DiscoveredDeviceFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_promotion_requires_manufacturer() -> None:
    """Anonymous discoveries cannot select a manufacturer integration."""
    discovered = DiscoveredDeviceFactory.build(manufacturer=None)

    assert DevicePromotionService().promote_discovered_device(discovered) == (
        False,
        "No manufacturer specified for discovered device",
        None,
    )


def test_promotion_rejects_existing_chassis(monkeypatch: pytest.MonkeyPatch) -> None:
    """An already-managed discovery returns its existing chassis for callers."""
    discovered = DiscoveredDeviceFactory.build()
    existing = object()
    service = DevicePromotionService()
    monkeypatch.setattr(
        service, "_find_existing_chassis_for_discovered", Mock(return_value=existing)
    )

    success, message, chassis = service.promote_discovered_device(discovered)

    assert success is False
    assert "Device already managed as chassis" in message
    assert chassis is existing


def test_promotion_reports_unavailable_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing integration support produces a stable failed result."""
    discovered = DiscoveredDeviceFactory.build()
    service = DevicePromotionService()
    monkeypatch.setattr(service, "_find_existing_chassis_for_discovered", Mock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_plugin_and_device_data_for_promotion",
        Mock(return_value=(None, None)),
    )

    assert service.promote_discovered_device(discovered) == (
        False,
        "Plugin not available for manufacturer",
        None,
    )


def test_promotion_creates_basic_chassis_without_api_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reachable discoveries remain manageable when detailed API inventory is absent."""
    discovered = DiscoveredDeviceFactory.build()
    plugin = object()
    basic = object()
    service = DevicePromotionService()
    monkeypatch.setattr(service, "_find_existing_chassis_for_discovered", Mock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_plugin_and_device_data_for_promotion",
        Mock(return_value=(plugin, None)),
    )
    create = Mock(return_value=basic)
    monkeypatch.setattr(WirelessChassisPersistenceService, "create", create)

    assert service.promote_discovered_device(discovered) == (
        True,
        "Created basic chassis (limited API data)",
        basic,
    )
    assert create.call_args.kwargs["manufacturer"] is discovered.manufacturer
    assert create.call_args.kwargs["write"].api_device_id == discovered.ip


def test_promotion_delegates_detailed_api_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detailed manufacturer data proceeds through normalized promotion."""
    discovered = DiscoveredDeviceFactory.build()
    plugin = object()
    data = {"id": "device-1"}
    expected = (True, "promoted", object())
    service = DevicePromotionService()
    monkeypatch.setattr(service, "_find_existing_chassis_for_discovered", Mock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_plugin_and_device_data_for_promotion",
        Mock(return_value=(plugin, data)),
    )
    promote = Mock(return_value=expected)
    monkeypatch.setattr(service, "_attempt_promotion_with_device_data", promote)

    assert service.promote_discovered_device(discovered) == expected
    promote.assert_called_once_with(discovered, plugin, data)


def test_promotion_contains_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Promotion exceptions remain inside the service boundary."""
    discovered = DiscoveredDeviceFactory.build(ip="192.0.2.150")
    service = DevicePromotionService()
    secret = "database-password-in-error"
    monkeypatch.setattr(
        service,
        "_find_existing_chassis_for_discovered",
        Mock(side_effect=RuntimeError(secret)),
    )

    result = service.promote_discovered_device(discovered)
    assert result == (
        False,
        "Promotion failed (RuntimeError); details redacted.",
        None,
    )
    assert secret not in str(result)


def test_find_existing_chassis_scopes_address_to_manufacturer() -> None:
    """Existing inventory identity includes both address and manufacturer."""
    existing = WirelessChassisFactory(ip="192.0.2.151")
    discovered = DiscoveredDeviceFactory.build(
        ip=existing.ip,
        manufacturer=existing.manufacturer,
    )
    unmatched = DiscoveredDeviceFactory(ip="192.0.2.152")
    service = DevicePromotionService()

    assert service._find_existing_chassis_for_discovered(discovered) == existing
    assert service._find_existing_chassis_for_discovered(unmatched) is None


def test_plugin_device_lookup_handles_missing_plugin_and_empty_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plugin lookup distinguishes unsupported integrations from empty inventory."""
    discovered = DiscoveredDeviceFactory.build()
    registry_lookup = Mock(
        side_effect=[
            ModuleNotFoundError("no integration"),
            Mock(get_devices=Mock(return_value=None)),
        ]
    )
    monkeypatch.setattr(
        "micboard.services.common.base.plugin.build_manufacturer_plugin",
        registry_lookup,
    )
    service = DevicePromotionService()

    assert service._get_plugin_and_device_data_for_promotion(discovered) == (None, None)
    plugin, data = service._get_plugin_and_device_data_for_promotion(discovered)
    assert plugin is not None
    assert data is None


@pytest.mark.parametrize("address_key", ["ip", "ipAddress"])
def test_plugin_device_lookup_matches_supported_address_alias(
    address_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Promotion finds device detail from either documented manufacturer address key."""
    discovered = DiscoveredDeviceFactory.build(ip="192.0.2.153")
    matched = {address_key: discovered.ip}
    plugin = Mock()
    plugin.get_devices.return_value = [{"ip": "192.0.2.254"}, matched]
    lookup = Mock(return_value=plugin)
    monkeypatch.setattr(
        "micboard.services.common.base.plugin.build_manufacturer_plugin",
        lookup,
    )

    assert DevicePromotionService()._get_plugin_and_device_data_for_promotion(discovered) == (
        plugin,
        matched,
    )
    lookup.assert_called_once_with(discovered.manufacturer)


def test_plugin_device_lookup_contains_inventory_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed detail fetch falls back to basic chassis promotion."""
    discovered = DiscoveredDeviceFactory.build()
    plugin = Mock()
    plugin.get_devices.side_effect = TimeoutError("timed out")
    monkeypatch.setattr(
        "micboard.services.common.base.plugin.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )

    assert DevicePromotionService()._get_plugin_and_device_data_for_promotion(discovered) == (
        plugin,
        None,
    )


@pytest.mark.parametrize(("channels", "expected_channels"), [(0, 4), (8, 8)])
def test_basic_chassis_creation_preserves_discovery_identity(
    channels: int,
    expected_channels: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Basic promotion retains discovery identity and applies a safe channel default."""
    discovered = DiscoveredDeviceFactory(
        ip=f"192.0.2.{160 + channels}",
        device_type="receiver",
        channels=channels,
    )

    service = DevicePromotionService()
    monkeypatch.setattr(service, "_find_existing_chassis_for_discovered", Mock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_plugin_and_device_data_for_promotion",
        Mock(return_value=(object(), None)),
    )

    success, _message, chassis = service.promote_discovered_device(discovered)

    assert success is True
    assert chassis is not None
    assert chassis.manufacturer == discovered.manufacturer
    assert chassis.api_device_id == discovered.ip
    assert chassis.ip == discovered.ip
    assert chassis.max_channels == expected_channels
    assert chassis.status == "discovered"


def _dedup_result(**overrides: object) -> SimpleNamespace:
    values = {
        "is_conflict": False,
        "conflict_type": None,
        "is_duplicate": False,
        "is_moved": False,
        "existing_device": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _promotion_inputs() -> tuple[object, Mock, dict[str, str], NormalizedChassis]:
    discovered = DiscoveredDeviceFactory.build()
    plugin = Mock()
    data = {"id": "device-1", "ip": discovered.ip}
    device = NormalizedChassis(
        api_device_id="device-1",
        ip=discovered.ip,
        serial_number="serial-1",
        mac_address="00:11:22:33:44:55",
    )
    plugin.normalize_device.return_value = device
    return discovered, plugin, data, device


@pytest.mark.parametrize("normalized", [None, NormalizedChassis(api_device_id="device-1")])
def test_detailed_promotion_requires_an_addressed_normalized_device(
    normalized: NormalizedChassis | None,
) -> None:
    """Manufacturer data that cannot be normalized, or names no address, is not persisted."""
    discovered, plugin, data, _device = _promotion_inputs()
    plugin.normalize_device.return_value = normalized

    assert DevicePromotionService()._attempt_promotion_with_device_data(
        discovered, plugin, data
    ) == (False, "Failed to normalize device data", None)


def test_detailed_promotion_deduplicates_on_normalized_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deduplication reads the normalized identity, and conflicts stop promotion."""
    discovered, plugin, data, device = _promotion_inputs()
    check = Mock(return_value=_dedup_result(is_conflict=True, conflict_type="ip_conflict"))
    monkeypatch.setattr("micboard.services.deduplication.check.check_device", check)

    assert DevicePromotionService()._attempt_promotion_with_device_data(
        discovered, plugin, data
    ) == (False, "Device conflict: ip_conflict", None)
    check.assert_called_once_with(
        serial_number=device.serial_number,
        mac_address=device.mac_address,
        ip=device.ip,
        api_device_id=device.api_device_id,
        manufacturer=discovered.manufacturer,
    )


def test_duplicate_promotion_updates_the_existing_chassis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate inventory is refreshed from the one normalized payload."""
    discovered, plugin, data, device = _promotion_inputs()
    existing = object()
    monkeypatch.setattr(
        "micboard.services.deduplication.check.check_device",
        Mock(return_value=_dedup_result(is_duplicate=True, existing_device=existing)),
    )
    update = Mock()
    monkeypatch.setattr(
        "micboard.services.sync.device_promotion_service."
        "WirelessChassisPersistenceService.update_from_normalized",
        update,
    )

    result = DevicePromotionService()._attempt_promotion_with_device_data(
        discovered,
        plugin,
        data,
    )

    assert result == (True, "Updated existing chassis", existing)
    update.assert_called_once_with(chassis=existing, payload=device)
    plugin.normalize_device.assert_called_once_with(data)


def test_new_promotion_creates_from_the_normalized_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New chassis creation uses the same normalized payload deduplication checked."""
    discovered, plugin, data, device = _promotion_inputs()
    created = object()
    monkeypatch.setattr(
        "micboard.services.deduplication.check.check_device",
        Mock(return_value=_dedup_result()),
    )
    create = Mock(return_value=created)
    monkeypatch.setattr(
        "micboard.services.sync.device_promotion_service."
        "WirelessChassisPersistenceService.create_from_normalized",
        create,
    )

    result = DevicePromotionService()._attempt_promotion_with_device_data(
        discovered,
        plugin,
        data,
    )

    assert result == (True, "Created new managed chassis", created)
    create.assert_called_once_with(payload=device, manufacturer=discovered.manufacturer)
