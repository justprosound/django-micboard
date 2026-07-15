"""Behavioral coverage for the discovery-list synchronization service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from micboard.services.sync.discovery_service import DiscoveryService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_manufacturer_discovery_reconciles_remote_and_local_candidates() -> None:
    manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.31")
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = ["192.0.2.30", "192.0.2.33"]
    plugin.add_discovery_ips.return_value = True
    plugin.remove_discovery_ips.return_value = True

    with (
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch(
            "micboard.services.sync.discovery_service.prepare_scanning_data",
            return_value=(
                {"192.0.2.0/24": ["192.0.2.32"]},
                {"receiver.example": ["192.0.2.34"]},
                2,
                True,
            ),
        ),
    ):
        succeeded = DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=16,
        )

    plugin.get_discovery_ips.assert_called_once_with()
    assert succeeded.success is True
    assert succeeded.sources_complete is True
    assert succeeded.remote_source_complete is True
    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.31", "192.0.2.32", "192.0.2.34"])
    plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.30", "192.0.2.33"])


def test_manufacturer_discovery_batches_candidate_queries_and_vendor_calls(
    django_assert_num_queries,
) -> None:
    """Candidate volume does not increase reconciliation queries or API calls."""
    manufacturer = ManufacturerFactory()
    chassis = [
        WirelessChassisFactory(
            manufacturer=manufacturer,
            ip=f"192.0.2.{address}",
        )
        for address in range(60, 70)
    ]
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = []
    plugin.add_discovery_ips.return_value = True

    with (
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        django_assert_num_queries(2),
    ):
        succeeded = DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once()
    assert set(plugin.add_discovery_ips.call_args.args[0]) == {device.ip for device in chassis}
    plugin.remove_discovery_ips.assert_not_called()
    assert succeeded.success is True


def test_manufacturer_discovery_excludes_candidates_owned_by_another_vendor() -> None:
    """Batch reconciliation preserves cross-manufacturer IP exclusivity."""
    manufacturer = ManufacturerFactory()
    other_manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=other_manufacturer, ip="192.0.2.71")
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = ["192.0.2.71"]
    plugin.add_discovery_ips.return_value = True
    plugin.remove_discovery_ips.return_value = True

    with (
        patch(
            "micboard.services.sync.discovery_service.collect_local_candidates",
            return_value=(["192.0.2.70", "192.0.2.71"], True),
        ),
        patch(
            "micboard.services.sync.discovery_service.prepare_scanning_data",
            return_value=({}, {}, 0, True),
        ),
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
    ):
        succeeded = DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.70"])
    plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.71"])
    assert succeeded.success is True


@pytest.mark.parametrize("failure", [False, RuntimeError("vendor unavailable")])
def test_manufacturer_discovery_contains_batch_write_failures(failure: object) -> None:
    """A failed vendor add or remove batch does not abort the discovery task."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = ["192.0.2.73"]
    if isinstance(failure, Exception):
        plugin.add_discovery_ips.side_effect = failure
        plugin.remove_discovery_ips.side_effect = failure
    else:
        plugin.add_discovery_ips.return_value = failure
        plugin.remove_discovery_ips.return_value = failure

    with (
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch(
            "micboard.services.sync.discovery_service.collect_local_candidates",
            return_value=(["192.0.2.72"], True),
        ),
    ):
        succeeded = DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.72"])
    plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.73"])
    assert succeeded.success is False


def test_manufacturer_discovery_recovers_when_remote_list_cannot_be_read() -> None:
    manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.40")
    plugin = MagicMock()
    plugin.get_discovery_ips.side_effect = RuntimeError("read failed")
    plugin.add_discovery_ips.return_value = True

    with (
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
    ):
        succeeded = DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.40"])
    plugin.remove_discovery_ips.assert_not_called()
    assert succeeded.success is False


def test_manufacturer_discovery_treats_empty_remote_response_as_no_candidates() -> None:
    """Vendor clients returning no collection do not break local reconciliation."""
    manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.41")
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = None
    plugin.add_discovery_ips.return_value = True

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ):
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.41"])
    plugin.remove_discovery_ips.assert_not_called()
