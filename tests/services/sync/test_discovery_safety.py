"""Failure-safety contracts for discovery desired-state reconciliation."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from micboard.services.sync.discovery_service import DiscoveryService
from tests.factories.discovery import DiscoveryFQDNFactory, ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_incomplete_discovery_still_removes_proven_cross_vendor_conflicts() -> None:
    """Source outages preserve uncertain entries without retaining known ownership conflicts."""
    manufacturer = ManufacturerFactory()
    other_manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=other_manufacturer, ip="192.0.2.75")
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = ["192.0.2.75", "192.0.2.76"]
    plugin.remove_discovery_ips.return_value = True

    with (
        patch(
            "micboard.services.sync.discovery_service.collect_local_candidates",
            return_value=["192.0.2.75"],
        ),
        patch(
            "micboard.services.sync.discovery_service.prepare_scanning_data",
            return_value=({}, {}, 0, False),
        ),
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
    ):
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=True,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_not_called()
    plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.75"])


def test_manufacturer_discovery_aborts_before_vendor_writes_when_local_read_fails() -> None:
    """An unavailable authoritative local source cannot be mistaken for empty desired state."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()

    with (
        patch(
            "micboard.services.sync.discovery_service.collect_local_candidates",
            side_effect=RuntimeError("database unavailable"),
        ),
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ) as get_plugin,
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    get_plugin.assert_not_called()
    plugin.get_discovery_ips.assert_not_called()
    plugin.add_discovery_ips.assert_not_called()
    plugin.remove_discovery_ips.assert_not_called()


def test_manufacturer_discovery_suppresses_removals_when_dns_is_incomplete() -> None:
    """Transient DNS failures preserve remote entries until desired state is complete."""
    manufacturer = ManufacturerFactory()
    DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn="receiver.example.test")
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = ["198.51.100.41"]

    with (
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch(
            "micboard.discovery.network_utils.socket.getaddrinfo",
            side_effect=socket.gaierror("resolver unavailable"),
        ),
    ):
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=True,
            max_hosts=16,
        )

    plugin.get_discovery_ips.assert_called_once_with()
    plugin.add_discovery_ips.assert_not_called()
    plugin.remove_discovery_ips.assert_not_called()
