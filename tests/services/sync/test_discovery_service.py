"""Behavioral coverage for the discovery-list synchronization service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from micboard.services.sync.discovery_service import DiscoveryService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_add_candidate_rejects_ip_owned_by_another_manufacturer() -> None:
    owner = ManufacturerFactory()
    current = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=owner, ip="192.0.2.10")
    plugin = MagicMock()

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ):
        added = DiscoveryService().add_discovery_candidate("192.0.2.10", current)

    assert added is False
    plugin.add_discovery_ips.assert_not_called()


@pytest.mark.parametrize("plugin_result", [True, False])
def test_add_candidate_returns_plugin_result(plugin_result: bool) -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.add_discovery_ips.return_value = plugin_result

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ):
        added = DiscoveryService().add_discovery_candidate(
            "192.0.2.11",
            manufacturer,
            source="manual-test",
        )

    assert added is plugin_result
    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.11"])


def test_add_candidate_contains_plugin_failure() -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.add_discovery_ips.side_effect = RuntimeError("vendor unavailable")

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ):
        added = DiscoveryService().add_discovery_candidate("192.0.2.12", manufacturer)

    assert added is False


@pytest.mark.parametrize("plugin_result", [True, False])
def test_remove_candidate_returns_plugin_result(plugin_result: bool) -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.remove_discovery_ips.return_value = plugin_result

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ):
        removed = DiscoveryService().remove_discovery_candidate("192.0.2.20", manufacturer)

    assert removed is plugin_result
    plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.20"])


def test_remove_candidate_contains_plugin_failure() -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.remove_discovery_ips.side_effect = RuntimeError("vendor unavailable")

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ):
        removed = DiscoveryService().remove_discovery_candidate("192.0.2.21", manufacturer)

    assert removed is False


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
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=16,
        )

    plugin.get_discovery_ips.assert_called_once_with()
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
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once()
    assert set(plugin.add_discovery_ips.call_args.args[0]) == {device.ip for device in chassis}
    plugin.remove_discovery_ips.assert_not_called()


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
            return_value=["192.0.2.70", "192.0.2.71"],
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
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.70"])
    plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.71"])


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
            return_value=["192.0.2.72"],
        ),
    ):
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.72"])
    plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.73"])


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
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=16,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.40"])
    plugin.remove_discovery_ips.assert_not_called()


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


def test_global_discovery_processes_every_manufacturer() -> None:
    manufacturers = [ManufacturerFactory(), ManufacturerFactory()]
    plugins = {manufacturer.pk: MagicMock() for manufacturer in manufacturers}
    for plugin in plugins.values():
        plugin.get_discovery_ips.return_value = []

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        side_effect=lambda manufacturer: plugins[manufacturer.pk],
    ):
        DiscoveryService().run_global_discovery(
            scan_cidrs=False,
            scan_fqdns=False,
            max_hosts=8,
        )

    assert all(plugin.get_discovery_ips.call_count == 1 for plugin in plugins.values())


def test_trigger_discovery_ignores_empty_manufacturer_pk() -> None:
    with (
        patch("micboard.utils.dependencies.huey_is_configured") as configured,
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
    ):
        DiscoveryService.trigger_manufacturer_discovery(0)

    configured.assert_not_called()
    enqueue.assert_not_called()


def test_trigger_discovery_enqueues_native_huey_task() -> None:
    manufacturer = ManufacturerFactory()

    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
        patch("micboard.tasks.sync.discovery.run_manufacturer_discovery_task") as discovery_task,
    ):
        DiscoveryService.trigger_manufacturer_discovery(
            manufacturer.pk,
            scan_cidrs=False,
            scan_fqdns=True,
        )

    enqueue.assert_called_once_with(discovery_task, manufacturer.pk, False, True)


@pytest.mark.parametrize("enqueue_fails", [False, True])
def test_trigger_discovery_runs_synchronously_when_queue_is_unavailable(
    enqueue_fails: bool,
) -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = []
    configured = enqueue_fails
    enqueue_side_effect = RuntimeError("queue unavailable") if enqueue_fails else None

    with (
        patch(
            "micboard.utils.dependencies.huey_is_configured",
            return_value=configured,
        ),
        patch(
            "micboard.utils.dependencies.enqueue_huey_task",
            side_effect=enqueue_side_effect,
        ),
        patch("micboard.tasks.sync.discovery.run_manufacturer_discovery_task"),
        patch(
            "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
    ):
        DiscoveryService.trigger_manufacturer_discovery(
            manufacturer.pk,
            scan_cidrs=False,
            scan_fqdns=False,
        )

    plugin.get_discovery_ips.assert_called_once_with()


def test_trigger_discovery_contains_missing_manufacturer() -> None:
    with patch("micboard.utils.dependencies.huey_is_configured", return_value=False):
        DiscoveryService.trigger_manufacturer_discovery(999_999)


def test_managed_ip_queries_use_persisted_chassis() -> None:
    managed_manufacturer = ManufacturerFactory()
    other_manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=managed_manufacturer, ip="192.0.2.50")
    WirelessChassisFactory(manufacturer=other_manufacturer, ip="192.0.2.51")
    service = DiscoveryService()

    assert service.get_all_managed_ips() == {"192.0.2.50", "192.0.2.51"}
    assert service.get_manufacturer_for_ip("192.0.2.50") == managed_manufacturer
    assert service.get_manufacturer_for_ip("192.0.2.99") is None
