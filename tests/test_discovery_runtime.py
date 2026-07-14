"""Coverage for discovery candidate, orchestration, and refresh boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice, DiscoveryCIDR, DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.device_refresh_service import DeviceRefreshService
from micboard.services.sync.discovery_candidates_service import DiscoveryCandidateService
from micboard.services.sync.discovery_orchestration_service import DiscoveryOrchestrationService
from micboard.services.sync.discovery_service import DiscoveryService


def _manufacturer(code: str = "test") -> Any:
    return SimpleNamespace(code=code, name=code.title())


def test_discovery_candidate_rejects_ip_owned_by_another_manufacturer() -> None:
    service = cast(Any, DiscoveryService())
    service._is_ip_managed_by_another_manufacturer = Mock(return_value=True)
    service._get_manufacturer_plugin = Mock()

    assert not service.add_discovery_candidate("192.0.2.1", _manufacturer())
    service._get_manufacturer_plugin.assert_not_called()


@pytest.mark.parametrize("client_result", [True, False])
def test_discovery_candidate_returns_client_result(client_result: bool) -> None:
    service = cast(Any, DiscoveryService())
    plugin = Mock()
    plugin.add_discovery_ips.return_value = client_result
    service._is_ip_managed_by_another_manufacturer = Mock(return_value=False)
    service._get_manufacturer_plugin = Mock(return_value=plugin)

    assert (
        service.add_discovery_candidate("192.0.2.1", _manufacturer(), source="test")
        is client_result
    )
    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.1"])


def test_discovery_candidate_contains_client_exception() -> None:
    service = cast(Any, DiscoveryService())
    plugin = Mock()
    plugin.add_discovery_ips.side_effect = RuntimeError("api unavailable")
    service._is_ip_managed_by_another_manufacturer = Mock(return_value=False)
    service._get_manufacturer_plugin = Mock(return_value=plugin)

    assert not service.add_discovery_candidate("192.0.2.1", _manufacturer())


@patch.object(Manufacturer.objects, "get", side_effect=Manufacturer.DoesNotExist)
def test_candidate_lookup_returns_empty_for_unknown_manufacturer(_get: MagicMock) -> None:
    assert DiscoveryCandidateService().get_discovery_candidates("missing") == []


@patch("micboard.services.sync.discovery_candidates_service.cache")
@patch.object(Manufacturer.objects, "get", side_effect=Manufacturer.DoesNotExist)
def test_progress_lookup_records_unknown_manufacturer(_get: MagicMock, cache: MagicMock) -> None:
    assert (
        DiscoveryCandidateService().compute_discovery_candidates_with_progress("missing", "status")
        == []
    )
    assert cache.set.call_args.args[1]["status"] == "error"


@patch.object(WirelessChassis.objects, "filter")
@patch("micboard.services.sync.discovery_candidates_service.get_manufacturer_plugin_instance")
def test_base_candidates_merge_remote_and_local_ips(
    get_plugin: MagicMock,
    chassis_filter: MagicMock,
) -> None:
    get_plugin.return_value.get_discovery_ips.return_value = ["192.0.2.1", None, 4]
    chassis_filter.return_value = [SimpleNamespace(ip="192.0.2.2"), SimpleNamespace(ip=None)]
    result = DiscoveryCandidateService()._collect_base_candidates(_manufacturer())
    assert result == ["192.0.2.1", "192.0.2.2"]


@patch.object(WirelessChassis.objects, "filter", side_effect=RuntimeError("db"))
@patch("micboard.services.sync.discovery_candidates_service.get_manufacturer_plugin_instance")
def test_base_candidates_contain_remote_and_database_failures(
    get_plugin: MagicMock,
    _chassis_filter: MagicMock,
) -> None:
    get_plugin.return_value.get_discovery_ips.side_effect = RuntimeError("api")
    assert DiscoveryCandidateService()._collect_base_candidates(_manufacturer()) == []


@patch("micboard.services.sync.discovery_candidates_service.resolve_fqdns")
@patch.object(DiscoveryFQDN.objects, "filter")
@patch.object(DiscoveryCIDR.objects, "filter")
def test_scanning_data_limits_cidrs_and_filters_resolutions(
    cidr_filter: MagicMock,
    fqdn_filter: MagicMock,
    resolve: MagicMock,
) -> None:
    cidr_filter.return_value = [SimpleNamespace(cidr="192.0.2.0/29")]
    fqdn_filter.return_value = [SimpleNamespace(fqdn="receiver.example.test")]
    resolve.return_value = ({"receiver.example.test": ["198.51.100.3", None]}, True)
    cidrs, fqdns, total = DiscoveryCandidateService()._prepare_scanning_data(
        _manufacturer(), True, True, 2
    )
    assert cidrs == {"192.0.2.0/29": ["192.0.2.1", "192.0.2.2"]}
    assert fqdns == {"receiver.example.test": ["198.51.100.3"]}
    assert total == 3


@patch("micboard.services.sync.discovery_candidates_service.resolve_fqdns")
@patch.object(DiscoveryFQDN.objects, "filter")
@patch.object(DiscoveryCIDR.objects, "filter")
def test_scanning_data_contains_invalid_network_and_dns_errors(
    cidr_filter: MagicMock,
    fqdn_filter: MagicMock,
    resolve: MagicMock,
) -> None:
    cidr_filter.return_value = [SimpleNamespace(cidr="invalid")]
    fqdn_filter.return_value = [SimpleNamespace(fqdn="missing.example.test")]
    resolve.side_effect = OSError("dns")
    cidrs, fqdns, total = DiscoveryCandidateService()._prepare_scanning_data(
        _manufacturer(), True, True, 10
    )
    assert cidrs == {"invalid": []}
    assert fqdns == {"missing.example.test": []}
    assert total == 0


@patch(
    "micboard.services.sync.discovery_candidates_service.BroadcastService.broadcast_progress_update"
)
@patch("micboard.services.sync.discovery_candidates_service.cache")
def test_progress_lifecycle_updates_cache_and_channel(
    cache: MagicMock,
    broadcast: MagicMock,
) -> None:
    service = cast(Any, DiscoveryCandidateService())
    service._init_progress_tracking("scan", 2)
    service._update_progress("scan", "scanning", 2, 1, current_cidr="192.0.2.0/30")
    cache.get.return_value = {"status": "running"}
    service._broadcast_progress("scan")
    result = service._finalize_candidates("scan", ["a", "a", "b"], 2, 2)
    assert result == ["a", "b"]
    assert cache.set.call_args.args[1]["status"] == "done"
    assert broadcast.call_count == 3


def test_scanning_hosts_reports_each_batch() -> None:
    service = cast(Any, DiscoveryCandidateService())
    service._update_progress = Mock()
    service._broadcast_progress = Mock()
    candidates = ["192.0.2.1"]
    hosts = [f"192.0.2.{value}" for value in range(1, 52)]
    processed = service._perform_scanning_with_progress(
        "scan",
        candidates,
        {"192.0.2.0/24": hosts},
        {"receiver.test": ["198.51.100.1"]},
        52,
    )
    assert processed == 52
    assert len(candidates) == 52
    service._broadcast_progress.assert_called_once()


@patch.object(Manufacturer.objects, "get")
def test_candidate_computation_deduplicates_combined_sources(get: MagicMock) -> None:
    get.return_value = _manufacturer()
    service = cast(Any, DiscoveryCandidateService())
    service._collect_base_candidates = Mock(return_value=["one", "two"])
    service._prepare_scanning_data = Mock(
        return_value=({"cidr": ["two", "three"]}, {"fqdn": ["one", "four"]}, 4)
    )
    assert service.get_discovery_candidates("test", scan_cidrs=True) == [
        "one",
        "two",
        "three",
        "four",
    ]


@patch.object(Manufacturer.objects, "get")
def test_progress_candidate_computation_runs_all_phases(get: MagicMock) -> None:
    get.return_value = _manufacturer()
    service = cast(Any, DiscoveryCandidateService())
    service._collect_base_candidates = Mock(return_value=["base"])
    service._prepare_scanning_data = Mock(return_value=({"cidr": ["scan"]}, {}, 1))
    service._init_progress_tracking = Mock()
    service._perform_scanning_with_progress = Mock(return_value=1)
    service._finalize_candidates = Mock(return_value=["base", "scan"])
    assert service.compute_discovery_candidates_with_progress("test", "status") == [
        "base",
        "scan",
    ]
    service._finalize_candidates.assert_called_once()


@patch(
    "micboard.services.sync.discovery_orchestration_service.DiscoveryOrchestrationService._emit_refresh_broadcast"
)
@patch("micboard.services.sync.hardware_sync_service.HardwareSyncService.bulk_sync_devices")
@patch("micboard.services.common.base.plugin.get_manufacturer_plugin")
@patch.object(Manufacturer.objects, "filter")
def test_discovery_request_syncs_and_broadcasts(
    manufacturer_filter: MagicMock,
    get_plugin: MagicMock,
    bulk_sync: MagicMock,
    emit: MagicMock,
) -> None:
    manufacturer = _manufacturer()
    manufacturer_filter.return_value = [manufacturer]
    get_plugin.return_value.return_value.get_devices.return_value = [{"ip": "192.0.2.1"}]
    bulk_sync.return_value = {"updated": 2, "added": 1}
    result = DiscoveryOrchestrationService.handle_discovery_requested(
        manufacturer_code="test", organization_id=7
    )
    assert result["test"] == {
        "status": "success",
        "device_count": 1,
        "updated": 2,
        "added": 1,
    }
    emit.assert_called_once()


@patch(
    "micboard.services.common.base.plugin.get_manufacturer_plugin",
    side_effect=RuntimeError("plugin"),
)
@patch.object(Manufacturer.objects, "all")
def test_discovery_request_contains_plugin_errors(
    manufacturer_all: MagicMock, _plugin: MagicMock
) -> None:
    manufacturer_all.return_value = [_manufacturer()]
    result = DiscoveryOrchestrationService.handle_discovery_requested()
    assert result["test"] == {"status": "error", "error": "plugin"}


def test_device_detail_requires_id() -> None:
    assert DiscoveryOrchestrationService.handle_device_detail_requested() == {
        "status": "error",
        "error": "device_id required",
    }


@patch("micboard.services.common.base.plugin.get_manufacturer_plugin")
@patch.object(Manufacturer.objects, "filter")
def test_device_detail_enriches_channels(
    manufacturer_filter: MagicMock, get_plugin: MagicMock
) -> None:
    manufacturer_filter.return_value = [_manufacturer()]
    plugin = get_plugin.return_value.return_value
    plugin.get_device.return_value = {"id": "one"}
    plugin.get_device_channels.return_value = [{"channel": 1}]
    result = DiscoveryOrchestrationService.handle_device_detail_requested(
        manufacturer_code="test", device_id="one"
    )
    assert result["test"]["device"]["channels"] == [{"channel": 1}]


@patch("micboard.services.common.base.plugin.get_manufacturer_plugin")
@patch.object(Manufacturer.objects, "all")
def test_device_detail_handles_not_found_and_plugin_error(
    manufacturer_all: MagicMock, get_plugin: MagicMock
) -> None:
    manufacturer_all.return_value = [_manufacturer()]
    plugin = get_plugin.return_value.return_value
    plugin.get_device.return_value = None
    assert DiscoveryOrchestrationService.handle_device_detail_requested(device_id="one") == {
        "status": "error",
        "error": "device not found",
    }
    plugin.get_device.side_effect = RuntimeError("api")
    result = DiscoveryOrchestrationService.handle_device_detail_requested(device_id="one")
    assert result["test"]["status"] == "error"


@pytest.mark.parametrize(
    ("device_state", "compatibility", "expected"),
    [
        ("ONLINE", "OK", DiscoveredDevice.STATUS_READY),
        ("DISCOVERED", "OK", DiscoveredDevice.STATUS_PENDING),
        ("ERROR", "OK", DiscoveredDevice.STATUS_ERROR),
        ("OFFLINE", "OK", DiscoveredDevice.STATUS_OFFLINE),
        ("UNKNOWN", "OK", DiscoveredDevice.STATUS_UNKNOWN),
        ("ONLINE", "INCOMPATIBLE_TOO_OLD", DiscoveredDevice.STATUS_INCOMPATIBLE),
    ],
)
def test_shure_field_extraction_maps_status(
    device_state: str, compatibility: str, expected: str
) -> None:
    model, api_id, metadata, status = DiscoveryOrchestrationService._extract_shure_fields(
        {
            "deviceState": device_state,
            "compatibility": compatibility,
            "hardwareIdentity": {"deviceId": "id"},
            "softwareIdentity": {"model": "RX"},
        }
    )
    assert (model, api_id, status) == ("RX", "id", expected)
    assert metadata["deviceState"] == device_state


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("online", DiscoveredDevice.STATUS_READY),
        ("inactive", DiscoveredDevice.STATUS_OFFLINE),
        ("fault", DiscoveredDevice.STATUS_ERROR),
        ("new", DiscoveredDevice.STATUS_PENDING),
    ],
)
def test_generic_field_extraction_maps_status(status: str, expected: str) -> None:
    model, api_id, metadata, mapped = DiscoveryOrchestrationService._extract_generic_fields(
        {"model": "RX", "id": "id", "status": status, "custom": True}
    )
    assert (model, api_id, mapped) == ("RX", "id", expected)
    assert metadata == {"status": status, "custom": True}


def test_common_field_extraction_accepts_protocol_address() -> None:
    assert DiscoveryOrchestrationService._extract_common_fields(
        {"communicationProtocol": {"address": "192.0.2.1"}, "channels": [1, 2]}
    ) == ("192.0.2.1", "unknown", 2)


@patch.object(DiscoveredDevice.objects, "update_or_create")
def test_discovered_device_persistence_handles_shure_generic_and_missing_ip(
    update_or_create: MagicMock,
) -> None:
    manufacturer = _manufacturer()
    DiscoveryOrchestrationService._persist_discovered_devices(
        [
            {
                "ip": "192.0.2.1",
                "hardwareIdentity": {"deviceId": "shure"},
                "softwareIdentity": {"model": "RX"},
                "deviceState": "ONLINE",
            },
            {"ipAddress": "192.0.2.2", "id": "generic", "status": "online"},
            {"id": "missing"},
        ],
        manufacturer,
    )
    assert update_or_create.call_count == 2


@patch("micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_update")
def test_refresh_broadcast_delegates_tenant_scope(broadcast: MagicMock) -> None:
    manufacturer = _manufacturer()
    DiscoveryOrchestrationService._emit_refresh_broadcast(manufacturer, [{}, {}], 4, 5)
    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        data={"device_count": 2},
        organization_id=4,
        campus_id=5,
    )


def _discovered(**overrides: Any) -> Any:
    values = {
        "pk": 1,
        "manufacturer": _manufacturer(),
        "ip": "192.0.2.1",
        "api_device_id": "device-1",
        "metadata": {},
        "model": "",
        "channels": 0,
        "status": DiscoveredDevice.STATUS_PENDING,
        "STATUS_READY": DiscoveredDevice.STATUS_READY,
        "STATUS_OFFLINE": DiscoveredDevice.STATUS_OFFLINE,
        "STATUS_ERROR": DiscoveredDevice.STATUS_ERROR,
        "save": Mock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_refresh_many_counts_success_and_failure() -> None:
    service = cast(Any, DeviceRefreshService())
    service._refresh_single_discovered_device = Mock(side_effect=[True, False, True])
    assert service.refresh_discovered_devices_from_api([1, 2, 3]) == (2, 1)


@patch("micboard.services.sync.device_refresh_service.get_manufacturer_plugin")
def test_refresh_single_applies_transformed_data(get_plugin: MagicMock) -> None:
    discovered = _discovered()
    plugin = get_plugin.return_value.return_value
    plugin.get_device.return_value = {"id": "device-1", "status": "ONLINE"}
    plugin.get_device_channels.return_value = [{"channel": 1}]
    plugin.transform_device_data.return_value = {
        "model": "RX",
        "api_device_id": "updated",
        "channels": "2",
        "status": "online",
    }
    assert DeviceRefreshService()._refresh_single_discovered_device(discovered)
    assert discovered.model == "RX"
    assert discovered.api_device_id == "updated"
    assert discovered.channels == 2
    assert discovered.status == DiscoveredDevice.STATUS_READY
    discovered.save.assert_called_once()


@patch("micboard.services.sync.device_refresh_service.get_manufacturer_plugin")
def test_refresh_single_rejects_missing_inputs_and_transform(get_plugin: MagicMock) -> None:
    service = DeviceRefreshService()
    assert not service._refresh_single_discovered_device(_discovered(manufacturer=None))

    get_plugin.return_value = None
    assert not service._refresh_single_discovered_device(_discovered())

    plugin = Mock(spec=[])
    get_plugin.return_value = Mock(return_value=plugin)
    assert not service._refresh_single_discovered_device(_discovered())


def test_device_data_lookup_falls_back_to_device_list() -> None:
    service = DeviceRefreshService()
    discovered = _discovered()
    plugin = MagicMock()
    plugin.get_device.side_effect = RuntimeError("detail")
    plugin.get_devices.return_value = [
        {"ip": "198.51.100.1"},
        {"ipAddress": "192.0.2.1", "id": "match"},
    ]
    device_data = service._get_device_data_from_plugin(plugin, discovered)
    assert device_data is not None
    assert device_data["id"] == "match"
    plugin.get_devices.side_effect = RuntimeError("list")
    assert service._get_device_data_from_plugin(plugin, discovered) is None


def test_channel_enrichment_and_transform_failures_are_contained() -> None:
    service = DeviceRefreshService()
    discovered = _discovered()
    plugin = MagicMock()
    data: dict[str, Any] = {}
    plugin.get_device_channels.return_value = [1]
    service._enrich_device_with_channels(plugin, discovered, data)
    assert data["channels"] == [1]
    plugin.transform_device_data.side_effect = RuntimeError("transform")
    assert service._transform_device(plugin, data, discovered) is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("ready", DiscoveredDevice.STATUS_READY),
        ("down", DiscoveredDevice.STATUS_OFFLINE),
        ("fault", DiscoveredDevice.STATUS_ERROR),
    ],
)
def test_apply_transformed_maps_status(status: str, expected: str) -> None:
    discovered = _discovered()
    DeviceRefreshService()._apply_transformed_to_discovered(
        discovered,
        {"channels": "invalid", "status": status},
        {"raw": True},
    )
    assert discovered.status == expected
    assert discovered.metadata == {"raw": True}
