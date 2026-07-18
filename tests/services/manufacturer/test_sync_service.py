"""Manufacturer synchronization orchestration and persistence contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from django.db import connection
from django.test import override_settings

import pytest

from micboard.models.discovery.discovery_queue import DeviceMovementLog
from micboard.services.core.hardware import NormalizedHardware
from micboard.services.deduplication.check import check_device
from micboard.services.deduplication.identity_index import DeviceIdentityIndex
from micboard.services.deduplication.result import DeduplicationResult
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.sync.polling_dtos import (
    DEFAULT_BROADCAST_CHUNK_SIZE,
    DEFAULT_MAX_POLL_DEVICES,
    HARD_MAX_POLL_DEVICES,
    ManufacturerPollLimits,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _payload(**overrides: object) -> NormalizedHardware:
    values = {
        "api_device_id": "device-1",
        "ip": "192.0.2.100",
        "serial_number": "serial-1",
        "mac_address": "00:11:22:33:44:55",
        "name": "Receiver",
        "model": "RX-1",
        "device_type": "receiver",
        "firmware_version": "1.0",
        "hosted_firmware_version": "1.1",
        "description": "Rack receiver",
        "subnet_mask": "255.255.255.0",
        "gateway": "192.0.2.1",
        "network_mode": "static",
        "interface_id": "eth0",
    }
    values.update(overrides)
    return NormalizedHardware(**values)  # type: ignore[arg-type]


def _result(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "success": True,
        "devices_added": 0,
        "devices_updated": 0,
        "devices_removed": 0,
        "errors": [],
        "devices_examined": 0,
        "device_limit": DEFAULT_MAX_POLL_DEVICES,
        "inventory_complete": True,
    }
    values.update(overrides)
    return values


def test_sync_reports_missing_manufacturer() -> None:
    """Unknown manufacturer codes fail before plugin discovery."""
    assert ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code="missing"
    ) == _result(success=False, errors=["Manufacturer not found or inactive: missing"])


def test_sync_reports_missing_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured manufacturers still require an installed integration."""
    ManufacturerFactory(code="vendor")
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=None),
    )

    assert ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")[
        "errors"
    ] == ["Plugin not found: vendor"]


def test_sync_returns_zero_counts_for_empty_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful empty manufacturer response is not treated as a failure."""
    ManufacturerFactory(code="vendor")
    plugin = Mock()
    plugin.get_devices.return_value = None
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )

    assert (
        ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")
        == _result()
    )


def test_sync_rechecks_activation_under_lock_after_vendor_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deactivation during vendor I/O prevents every subsequent inventory mutation."""
    manufacturer = ManufacturerFactory(code="vendor")
    plugin = Mock()

    def deactivate_during_request() -> list[dict[str, str]]:
        type(manufacturer).objects.filter(pk=manufacturer.pk).update(is_active=False)
        return [{"id": "raw"}]

    plugin.get_devices.side_effect = deactivate_during_request
    persist = Mock(return_value="created")
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[_payload()]),
    )
    monkeypatch.setattr(ManufacturerSyncService, "_sync_normalized_device", persist)

    result = ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code=manufacturer.code,
    )

    assert result == _result(
        success=False,
        errors=["Manufacturer became inactive during polling; no devices were synchronized."],
        devices_examined=1,
    )
    persist.assert_not_called()


def test_forced_sync_preserves_explicit_override_after_vendor_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an explicit operator force can persist after mid-request deactivation."""
    manufacturer = ManufacturerFactory(code="vendor")
    plugin = Mock()

    def deactivate_during_request() -> list[dict[str, str]]:
        type(manufacturer).objects.filter(pk=manufacturer.pk).update(is_active=False)
        return [{"id": "raw"}]

    plugin.get_devices.side_effect = deactivate_during_request
    persist = Mock(return_value="created")
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[_payload()]),
    )
    monkeypatch.setattr(ManufacturerSyncService, "_sync_normalized_device", persist)

    result = ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code=manufacturer.code,
        force=True,
    )

    assert result == _result(devices_added=1, devices_examined=1)
    persist.assert_called_once()


def test_sync_counts_created_and_updated_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only persisted create and update outcomes contribute to the summary."""
    ManufacturerFactory(code="vendor")
    plugin = Mock()
    plugin.get_devices.return_value = [{"id": "raw"}]
    payloads = [_payload(), _payload(api_device_id="device-2"), _payload(api_device_id="device-3")]
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(ManufacturerSyncService, "_normalize_devices", Mock(return_value=payloads))
    persist = Mock(side_effect=["created", "updated", None])
    monkeypatch.setattr(ManufacturerSyncService, "_sync_normalized_device", persist)

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert result == _result(devices_added=1, devices_updated=1, devices_examined=1)
    assert persist.call_count == 3


@override_settings(MICBOARD_POLL_MAX_DEVICES=2)
def test_sync_stops_at_limit_plus_one_and_refuses_partial_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Oversized generator responses are detected without draining or partially persisting them."""
    ManufacturerFactory(code="vendor")
    consumed: list[int] = []

    def inventory():
        for number in range(10):
            consumed.append(number)
            yield {"id": f"device-{number}", "ip": f"192.0.2.{number + 1}"}

    plugin = Mock()
    plugin.get_devices.return_value = inventory()
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert consumed == [0, 1, 2]
    assert result == _result(
        success=False,
        errors=[
            "Manufacturer inventory exceeded the configured device limit; "
            "no devices were synchronized."
        ],
        devices_examined=3,
        device_limit=2,
        inventory_complete=False,
    )
    plugin.transform_device_data.assert_not_called()


@override_settings(MICBOARD_POLL_MAX_DEVICES=100_000)
def test_poll_limit_is_clamped_to_package_hard_ceiling() -> None:
    """Host configuration cannot disable the package's finite inventory ceiling."""
    assert ManufacturerPollLimits.from_settings().max_devices == HARD_MAX_POLL_DEVICES


@override_settings(
    MICBOARD_POLL_MAX_DEVICES=True,
    MICBOARD_POLL_BROADCAST_CHUNK_SIZE="invalid",
)
def test_poll_limits_reject_boolean_and_invalid_host_values() -> None:
    """Malformed host values use safe defaults instead of disabling bounds."""
    limits = ManufacturerPollLimits.from_settings()

    assert limits.max_devices == DEFAULT_MAX_POLL_DEVICES
    assert limits.broadcast_chunk_size == DEFAULT_BROADCAST_CHUNK_SIZE


@override_settings(MICBOARD_POLL_MAX_DEVICES=0, MICBOARD_POLL_BROADCAST_CHUNK_SIZE=-1)
def test_poll_limits_clamp_nonpositive_host_values() -> None:
    """Numeric host limits remain positive."""
    limits = ManufacturerPollLimits.from_settings()

    assert limits.max_devices == 1
    assert limits.broadcast_chunk_size == 1


def test_bulk_identity_index_bounds_reads_for_large_batches(django_assert_num_queries) -> None:
    """Identity lookup cost stays constant as the bounded payload count grows."""
    manufacturer = ManufacturerFactory(code="vendor")
    payloads = [
        _payload(
            api_device_id=f"device-{number}",
            ip=f"198.51.100.{number + 1}",
            serial_number=f"serial-{number}",
            mac_address=f"02:00:00:00:{number // 256:02x}:{number % 256:02x}",
        )
        for number in range(40)
    ]

    with django_assert_num_queries(4):
        identity_index = DeviceIdentityIndex.build(payloads, manufacturer=manufacturer)

    with django_assert_num_queries(0):
        results = [
            check_device(
                serial_number=payload.serial_number,
                mac_address=payload.mac_address,
                ip=payload.ip,
                api_device_id=payload.api_device_id,
                manufacturer=manufacturer,
                identity_index=identity_index,
            )
            for payload in payloads
        ]

    assert all(result.is_new for result in results)


def test_bulk_identity_index_chunks_reads_below_backend_parameter_limits(
    django_assert_num_queries,
) -> None:
    """Large allowed batches use fixed-size bulk reads instead of per-device lookups."""
    manufacturer = ManufacturerFactory(code="vendor")
    payloads = [
        _payload(
            api_device_id=f"device-{number}",
            ip=f"10.0.{number // 256}.{number % 256}",
            serial_number=f"serial-{number}",
            mac_address=(
                f"02:00:00:{(number >> 16) & 0xFF:02x}:"
                f"{(number >> 8) & 0xFF:02x}:{number & 0xFF:02x}"
            ),
        )
        for number in range(1_001)
    ]

    with django_assert_num_queries(19):
        DeviceIdentityIndex.build(payloads, manufacturer=manufacturer)


def test_persistence_locks_before_rebuilding_identity_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DB-backed global lock closes the identity-index/write race window."""
    from micboard.models.discovery.manufacturer import Manufacturer

    manufacturer = ManufacturerFactory(code="serialized-vendor")
    payload = _payload()
    events: list[str] = []
    ordered_queryset = Mock()
    ordered_queryset.first.side_effect = lambda: events.append("sentinel-locked") or manufacturer
    lock_queryset = Mock()
    lock_queryset.only.return_value.order_by.return_value = ordered_queryset
    lock_queryset.get.side_effect = lambda **_kwargs: events.append("target-locked") or manufacturer
    select_for_update = Mock(return_value=lock_queryset)
    monkeypatch.setattr(Manufacturer.objects, "select_for_update", select_for_update)

    identity_index = object()
    identity_index_class = Mock()

    def build_index(*_args: object, **_kwargs: object) -> object:
        assert connection.in_atomic_block is True
        assert events == ["sentinel-locked", "target-locked"]
        events.append("indexed")
        return identity_index

    identity_index_class.build.side_effect = build_index

    def persist(*_args: object, **kwargs: object) -> str:
        assert connection.in_atomic_block is True
        assert events == ["sentinel-locked", "target-locked", "indexed"]
        assert kwargs["identity_index"] is identity_index
        events.append("written")
        return "created"

    monkeypatch.setattr(
        ManufacturerSyncService,
        "_sync_normalized_device",
        Mock(side_effect=persist),
    )

    result = ManufacturerSyncService._persist_normalized_devices(
        [payload],
        manufacturer=manufacturer,
        check_device=Mock(),
        identity_index_class=identity_index_class,
    )

    assert result == (1, 0)
    assert events == ["sentinel-locked", "target-locked", "indexed", "written"]
    assert select_for_update.call_count == 2
    lock_queryset.only.assert_called_once_with("pk")
    lock_queryset.only.return_value.order_by.assert_called_once_with("pk")
    lock_queryset.get.assert_called_once_with(pk=manufacturer.pk)


def test_persistence_rolls_back_earlier_mutation_when_later_payload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every poll mutation branch shares one atomic identity-lock transaction."""
    from micboard.models.hardware.wireless_chassis import WirelessChassis

    manufacturer = ManufacturerFactory(code="rollback-vendor")
    payloads = [_payload(), _payload(api_device_id="device-2", ip="192.0.2.101")]

    def persist(payload: NormalizedHardware, *_args: object, **_kwargs: object) -> str:
        if payload.api_device_id == "device-2":
            raise RuntimeError("simulated later write failure")
        WirelessChassisFactory(
            manufacturer=manufacturer,
            api_device_id=payload.api_device_id,
            ip=payload.ip,
        )
        return "created"

    monkeypatch.setattr(ManufacturerSyncService, "_sync_normalized_device", persist)
    identity_index_class = Mock()
    identity_index_class.build.return_value = object()

    with pytest.raises(RuntimeError, match="later write failure"):
        ManufacturerSyncService._persist_normalized_devices(
            payloads,
            manufacturer=manufacturer,
            check_device=Mock(),
            identity_index_class=identity_index_class,
        )

    assert not WirelessChassis.objects.filter(
        manufacturer=manufacturer,
        api_device_id="device-1",
    ).exists()


def test_persistence_refuses_to_write_without_a_lock_sentinel() -> None:
    """An absent row is never mistaken for a database-backed serialization lock."""
    from micboard.models.discovery.manufacturer import Manufacturer

    identity_index_class = Mock()

    with pytest.raises(Manufacturer.DoesNotExist, match="identity mutation lock is unavailable"):
        ManufacturerSyncService._persist_normalized_devices(
            [_payload()],
            manufacturer=SimpleNamespace(pk=404),
            check_device=Mock(),
            identity_index_class=identity_index_class,
        )

    identity_index_class.build.assert_not_called()


def test_bulk_identity_index_preserves_priority_and_tracks_batch_creates() -> None:
    """Indexed lookups retain serial-first semantics and expose new rows to later payloads."""
    manufacturer = ManufacturerFactory(code="vendor")
    existing = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="existing-api-id",
        serial_number="stable-serial",
        mac_address="02:00:00:00:10:00",
        ip="192.0.2.150",
    )
    first = _payload(
        api_device_id="incoming-api-id",
        serial_number=existing.serial_number,
        mac_address="02:00:00:00:10:01",
        ip=existing.ip,
    )
    second = _payload(
        api_device_id="batch-new",
        serial_number="batch-serial",
        mac_address="02:00:00:00:10:02",
        ip="192.0.2.151",
    )
    identity_index = DeviceIdentityIndex.build([first, second], manufacturer=manufacturer)

    serial_match = check_device(
        serial_number=first.serial_number,
        mac_address=first.mac_address,
        ip=first.ip,
        api_device_id=first.api_device_id,
        manufacturer=manufacturer,
        identity_index=identity_index,
    )
    assert serial_match.is_duplicate is True
    assert serial_match.existing_device == existing
    assert serial_match.details == {"match_type": "serial_number"}

    created = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id=second.api_device_id,
        serial_number=second.serial_number,
        mac_address=second.mac_address,
        ip=second.ip,
    )
    identity_index.add(created)
    later_match = check_device(
        serial_number=second.serial_number,
        mac_address=second.mac_address,
        ip=second.ip,
        api_device_id=second.api_device_id,
        manufacturer=manufacturer,
        identity_index=identity_index,
    )
    assert later_match.is_duplicate is True
    assert later_match.existing_device == created


@pytest.mark.parametrize(
    ("identity_field", "identity_value"),
    [
        ("serial_number", "foreign-sync-serial"),
        ("mac_address", "02:00:00:00:20:01"),
    ],
)
def test_sync_does_not_rehome_cross_vendor_identity_at_changed_ip(
    identity_field: str,
    identity_value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indexed manufacturer sync leaves foreign hardware ownership and address unchanged."""
    existing_manufacturer = ManufacturerFactory(code="existing-sync-owner")
    incoming_manufacturer = ManufacturerFactory(code="incoming-sync-owner")
    chassis = WirelessChassisFactory(
        manufacturer=existing_manufacturer,
        serial_number=(identity_value if identity_field == "serial_number" else ""),
        mac_address=(identity_value if identity_field == "mac_address" else None),
        ip="192.0.2.201",
        name="Foreign chassis",
        status="offline",
    )
    payload = _payload(
        api_device_id="incoming-sync-device",
        serial_number=(identity_value if identity_field == "serial_number" else ""),
        mac_address=(identity_value if identity_field == "mac_address" else ""),
        ip="192.0.2.202",
        name="Incoming chassis",
    )
    plugin = Mock()
    plugin.get_devices.return_value = [{"id": payload.api_device_id}]
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[payload]),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code=incoming_manufacturer.code,
    )

    assert result == _result(devices_examined=1)
    chassis.refresh_from_db()
    assert chassis.manufacturer == existing_manufacturer
    assert chassis.ip == "192.0.2.201"
    assert chassis.name == "Foreign chassis"
    assert chassis.status == "offline"
    assert not type(chassis).objects.filter(manufacturer=incoming_manufacturer).exists()


def test_sync_rejects_foreign_mac_hidden_behind_same_vendor_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The locked poll validates every durable identity before updating a serial match."""
    incoming_manufacturer = ManufacturerFactory(code="combined-sync-owner")
    foreign_manufacturer = ManufacturerFactory(code="combined-sync-foreign")
    serial_owner = WirelessChassisFactory(
        manufacturer=incoming_manufacturer,
        serial_number="combined-sync-serial",
        mac_address="02:00:00:00:30:01",
        ip="192.0.2.211",
        name="Protected serial owner",
        status="offline",
    )
    foreign_mac_owner = WirelessChassisFactory(
        manufacturer=foreign_manufacturer,
        serial_number="foreign-combined-sync-serial",
        mac_address="02:00:00:00:30:02",
        ip="192.0.2.212",
    )
    payload = _payload(
        api_device_id="combined-sync-incoming",
        serial_number=serial_owner.serial_number,
        mac_address=foreign_mac_owner.mac_address,
        ip="192.0.2.213",
        name="Untrusted update",
    )
    plugin = Mock()
    plugin.get_devices.return_value = [{"id": payload.api_device_id}]
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[payload]),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code=incoming_manufacturer.code,
    )

    assert result == _result(devices_examined=1)
    serial_owner.refresh_from_db()
    assert str(serial_owner.ip) == "192.0.2.211"
    assert serial_owner.name == "Protected serial owner"
    assert serial_owner.status == "offline"


def test_sync_rejects_foreign_existing_device_even_if_deduplication_misclassifies_it() -> None:
    """Persistence boundary does not trust a moved result that crosses manufacturers."""
    existing_manufacturer = ManufacturerFactory(code="existing-defense-owner")
    incoming_manufacturer = ManufacturerFactory(code="incoming-defense-owner")
    chassis = WirelessChassisFactory(
        manufacturer=existing_manufacturer,
        ip="192.0.2.203",
        name="Protected chassis",
        status="offline",
    )
    dedup_result = DeduplicationResult.moved(
        chassis,
        conflict_type="ip_changed",
    )

    outcome = ManufacturerSyncService._sync_normalized_device(
        _payload(ip="192.0.2.204", name="Attacker-controlled name"),
        incoming_manufacturer,
        Mock(return_value=dedup_result),
    )

    assert outcome is None
    chassis.refresh_from_db()
    assert chassis.manufacturer == existing_manufacturer
    assert chassis.ip == "192.0.2.203"
    assert chassis.name == "Protected chassis"
    assert chassis.status == "offline"


def test_bulk_identity_index_tracks_ipv6_moves_and_ambiguous_values() -> None:
    """Canonical IP updates and duplicate-key failures preserve queryset-get behavior."""
    manufacturer = ManufacturerFactory(code="vendor")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="ipv6-device",
        serial_number="",
        mac_address=None,
        ip="2001:db8::1",
    )
    payload = _payload(
        api_device_id=chassis.api_device_id,
        serial_number="",
        mac_address="",
        ip="2001:0db8:0:0:0:0:0:1",
    )
    identity_index = DeviceIdentityIndex.build([payload], manufacturer=manufacturer)

    assert identity_index.ip(payload.ip) == chassis
    identity_index.add(chassis)
    chassis.ip = "2001:db8::2"
    identity_index.move_ip(chassis, old_ip=payload.ip)
    assert identity_index.ip(payload.ip) is None
    assert identity_index.ip(chassis.ip) == chassis

    other = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="other-device",
        serial_number="ambiguous",
        ip="2001:db8::3",
    )
    identity_index.by_serial["ambiguous"] = [chassis, other]
    with pytest.raises(type(chassis).MultipleObjectsReturned):
        identity_index.serial("ambiguous")


def test_identity_query_chunks_support_backends_without_parameter_metadata() -> None:
    """Backends without a declared parameter ceiling still receive finite query chunks."""
    features_type = type(connection.features)
    with patch.object(
        features_type,
        "max_query_params",
        new_callable=PropertyMock,
        return_value=None,
    ):
        querysets = list(DeviceIdentityIndex._chunked_querysets("serial_number", {"one", "two"}))

    assert len(querysets) == 1


def test_sync_contains_manufacturer_api_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration exceptions become a failed result instead of escaping the task boundary."""
    ManufacturerFactory(code="vendor")
    plugin = Mock()
    secret = "manufacturer-secret-token"
    plugin.get_devices.side_effect = TimeoutError(secret)
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert result["success"] is False
    assert result["errors"] == ["Device synchronization failed (TimeoutError); details redacted."]
    assert secret not in str(result)


def test_normalization_skips_untransformable_and_incomplete_devices() -> None:
    """Only transformed payloads with an external ID and address reach persistence."""
    plugin = Mock()
    plugin.transform_device_data.side_effect = [
        None,
        {"id": "missing-address"},
        {"id": "complete", "ip": "192.0.2.110"},
    ]

    result = ManufacturerSyncService._normalize_devices([{}, {}, {}], plugin)

    assert result == [
        _payload(
            api_device_id="complete",
            ip="192.0.2.110",
            serial_number="",
            mac_address="",
            name="",
            model="",
            device_type="",
            firmware_version="",
            hosted_firmware_version="",
            description="",
            subnet_mask=None,
            gateway=None,
            network_mode="auto",
            interface_id="",
        )
    ]


@pytest.mark.parametrize(
    ("dedup", "expected", "update_ip", "reconciles_existing_status"),
    [
        (SimpleNamespace(is_conflict=True), None, False, False),
        (
            SimpleNamespace(
                is_conflict=False,
                is_moved=True,
                is_duplicate=False,
                is_new=False,
                existing_device=SimpleNamespace(
                    status="offline",
                    manufacturer_id=1,
                    pk=1,
                    ip="192.0.2.99",
                ),
            ),
            "updated",
            True,
            True,
        ),
        (
            SimpleNamespace(
                is_conflict=False,
                is_moved=False,
                is_duplicate=True,
                is_new=False,
                existing_device=SimpleNamespace(status="discovered", manufacturer_id=1, pk=1),
            ),
            "updated",
            False,
            True,
        ),
        (
            SimpleNamespace(
                is_conflict=False,
                is_moved=False,
                is_duplicate=True,
                is_new=False,
                existing_device=SimpleNamespace(status="maintenance", manufacturer_id=1, pk=1),
            ),
            "updated",
            False,
            False,
        ),
        (
            SimpleNamespace(
                is_conflict=False,
                is_moved=False,
                is_duplicate=False,
                is_new=True,
                existing_device=None,
            ),
            "created",
            False,
            False,
        ),
        (
            SimpleNamespace(
                is_conflict=False,
                is_moved=False,
                is_duplicate=False,
                is_new=False,
                existing_device=None,
            ),
            None,
            False,
            False,
        ),
    ],
)
def test_sync_normalized_device_applies_deduplication_outcome(
    dedup: SimpleNamespace,
    expected: str | None,
    update_ip: bool,
    reconciles_existing_status: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deduplication state controls whether a chassis is skipped, updated, or created."""
    payload = _payload()
    manufacturer = SimpleNamespace(pk=1)
    check_device = Mock(return_value=dedup)
    update = Mock()
    create = Mock(return_value=SimpleNamespace(status="offline"))
    reconcile_status = Mock()
    monkeypatch.setattr(WirelessChassisPersistenceService, "update_from_normalized", update)
    monkeypatch.setattr(WirelessChassisPersistenceService, "create_from_normalized", create)
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync._transition_responding_chassis_online",
        reconcile_status,
    )

    result = ManufacturerSyncService._sync_normalized_device(
        payload,
        manufacturer,
        check_device,
    )

    assert result == expected
    check_device.assert_called_once_with(
        serial_number=payload.serial_number,
        mac_address=payload.mac_address,
        ip=payload.ip,
        api_device_id=payload.api_device_id,
        manufacturer=manufacturer,
    )
    if update_ip:
        update.assert_called_once_with(
            chassis=dedup.existing_device,
            payload=payload,
            set_ip=True,
        )
    elif expected == "updated":
        update.assert_called_once_with(chassis=dedup.existing_device, payload=payload)
    else:
        update.assert_not_called()
    assert reconcile_status.called is reconciles_existing_status
    if expected == "created":
        assert create.call_args.kwargs["initial_status"] == "online"


def test_new_sync_chassis_is_created_in_its_final_online_state() -> None:
    """A responding new device avoids an invalid discovered-to-online follow-up save."""
    manufacturer = ManufacturerFactory(code="new-online-vendor")
    payload = _payload(
        api_device_id="new-online-device",
        serial_number="new-online-serial",
        ip="192.0.2.151",
    )

    result = ManufacturerSyncService._sync_normalized_device(
        payload,
        manufacturer,
        Mock(return_value=DeduplicationResult.new()),
    )

    chassis = manufacturer.wirelesschassis_set.get(api_device_id=payload.api_device_id)
    assert result == "created"
    assert chassis.status == "online"
    assert chassis.is_online is True
    assert chassis.last_online_at is not None


def test_moved_sync_device_records_address_audit_inside_persistence_flow() -> None:
    """A durable identity address change writes one explicit movement record."""
    manufacturer = ManufacturerFactory(code="movement-audit-vendor")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="movement-device",
        serial_number="movement-serial",
        ip="192.0.2.160",
        status="online",
    )
    payload = _payload(
        api_device_id=chassis.api_device_id,
        serial_number=chassis.serial_number,
        ip="192.0.2.161",
    )

    result = ManufacturerSyncService._sync_normalized_device(
        payload,
        manufacturer,
        Mock(
            return_value=DeduplicationResult.moved(
                chassis,
                conflict_type="ip_changed",
            )
        ),
    )

    chassis.refresh_from_db()
    movement = DeviceMovementLog.objects.get(device=chassis)
    assert result == "updated"
    assert str(chassis.ip) == "192.0.2.161"
    assert str(movement.old_ip) == "192.0.2.160"
    assert str(movement.new_ip) == "192.0.2.161"
    assert movement.detected_by == "manufacturer_sync"


def test_duplicate_discovered_chassis_transitions_through_provisioning() -> None:
    """A known discovered device reaches online through both legal lifecycle steps."""
    manufacturer = ManufacturerFactory(code="duplicate-online-vendor")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="duplicate-online-device",
        serial_number="duplicate-online-serial",
        ip="192.0.2.152",
        status="discovered",
    )
    payload = _payload(
        api_device_id=chassis.api_device_id,
        serial_number=chassis.serial_number,
        ip=str(chassis.ip),
    )

    result = ManufacturerSyncService._sync_normalized_device(
        payload,
        manufacturer,
        Mock(return_value=DeduplicationResult.duplicate(chassis)),
    )

    chassis.refresh_from_db()
    assert result == "updated"
    assert chassis.status == "online"
    assert chassis.is_online is True
    assert chassis.last_online_at is not None


def test_deduplication_omits_blank_optional_identities() -> None:
    """Blank serial and MAC fields are sent as absent deduplication keys."""
    check_device = Mock(
        return_value=SimpleNamespace(
            is_conflict=True,
        )
    )

    ManufacturerSyncService._sync_normalized_device(
        _payload(serial_number="", mac_address=""),
        object(),
        check_device,
    )

    assert check_device.call_args.kwargs["serial_number"] is None
    assert check_device.call_args.kwargs["mac_address"] is None


def test_indexed_move_refreshes_the_batch_ip_identity() -> None:
    """Later payloads in the locked batch see a chassis at its updated address."""
    chassis = SimpleNamespace(
        pk=1,
        manufacturer_id=1,
        ip="192.0.2.140",
        status="online",
    )
    dedup = SimpleNamespace(
        is_conflict=False,
        is_moved=True,
        is_duplicate=False,
        is_new=False,
        existing_device=chassis,
    )
    identity_index = Mock()
    update = Mock(
        side_effect=lambda *, chassis, payload, **_kwargs: setattr(chassis, "ip", payload.ip)
    )

    with (
        patch.object(WirelessChassisPersistenceService, "update_from_normalized", update),
        patch("micboard.services.manufacturer.sync.log_device_movement"),
    ):
        result = ManufacturerSyncService._sync_normalized_device(
            _payload(ip="192.0.2.141"),
            SimpleNamespace(pk=1),
            Mock(return_value=dedup),
            identity_index=identity_index,
        )

    assert result == "updated"
    identity_index.move_ip.assert_called_once_with(chassis, old_ip="192.0.2.140")
    assert chassis.ip == "192.0.2.141"


@pytest.mark.parametrize(
    ("device_type", "expected_role"),
    [
        ("IEM transmitter", "transmitter"),
        ("hybrid transceiver", "transceiver"),
        ("receiver", "receiver"),
        ("", "legacy"),
    ],
)
def test_update_existing_chassis_maps_role_and_preserves_blank_fields(
    device_type: str,
    expected_role: str,
) -> None:
    """Normalized values update inventory without erasing useful existing metadata."""
    chassis = SimpleNamespace(
        ip="192.0.2.120",
        name="Existing",
        model="Existing Model",
        role="legacy",
        firmware_version="old",
        hosted_firmware_version="old-hosted",
        description="existing description",
        subnet_mask="255.255.255.0",
        gateway="192.0.2.1",
        network_mode="static",
        interface_id="eth0",
        save=Mock(),
    )
    payload = _payload(device_type=device_type).model_copy(
        update={
            "name": "",
            "model": "",
            "firmware_version": "",
            "hosted_firmware_version": "",
            "description": "",
            "subnet_mask": None,
            "gateway": None,
            "network_mode": "",
            "interface_id": "",
        }
    )

    result = WirelessChassisPersistenceService.update_from_normalized(
        chassis=chassis,
        payload=payload,
        set_ip=True,
    )

    assert result is chassis
    assert chassis.ip == payload.ip
    assert chassis.name == "Existing"
    assert chassis.model == "Existing Model"
    assert chassis.role == expected_role
    assert chassis.firmware_version == "old"
    assert chassis.last_seen is not None
    assert chassis.save.call_args.kwargs["update_fields"][0] == "ip"


def test_update_existing_chassis_applies_nonblank_values_without_ip_change() -> None:
    """Ordinary duplicate refreshes update metadata while retaining the known address."""
    chassis = SimpleNamespace(
        ip="192.0.2.130",
        name="Old",
        model="Old",
        role="receiver",
        firmware_version="old",
        hosted_firmware_version="old",
        description="old",
        subnet_mask=None,
        gateway=None,
        network_mode="auto",
        interface_id="",
        save=Mock(),
    )

    WirelessChassisPersistenceService.update_from_normalized(
        chassis=chassis,
        payload=_payload(),
    )

    assert chassis.ip == "192.0.2.130"
    assert chassis.name == "Receiver"
    assert chassis.model == "RX-1"
    assert chassis.description == "Rack receiver"
    assert "ip" not in chassis.save.call_args.kwargs["update_fields"]


def test_update_existing_chassis_repairs_equivalent_legacy_mac_format() -> None:
    """A matched legacy row is safely rewritten at the canonical persistence boundary."""
    chassis = SimpleNamespace(
        ip="192.0.2.130",
        name="Old",
        model="Old",
        role="receiver",
        mac_address="AA-BB-CC-DD-EE-FF",
        firmware_version="old",
        hosted_firmware_version="old",
        description="old",
        subnet_mask=None,
        gateway=None,
        network_mode="auto",
        interface_id="",
        save=Mock(),
    )

    WirelessChassisPersistenceService.update_from_normalized(
        chassis=chassis,
        payload=_payload(mac_address="aabbccddeeff"),
    )

    assert chassis.mac_address == "aa:bb:cc:dd:ee:ff"
    assert "mac_address" in chassis.save.call_args.kwargs["update_fields"]


@pytest.mark.parametrize(
    ("device_type", "expected_role"),
    [("transmitter", "transmitter"), ("transceiver", "transceiver"), ("", "receiver")],
)
def test_create_chassis_maps_normalized_payload(
    device_type: str,
    expected_role: str,
) -> None:
    """New normalized devices produce a complete chassis creation request."""
    created = object()
    manager_create = Mock(return_value=created)
    manufacturer = object()
    with patch(
        "micboard.models.hardware.wireless_chassis.WirelessChassis.objects.create",
        manager_create,
    ):
        result = WirelessChassisPersistenceService.create_from_normalized(
            payload=_payload(device_type=device_type),
            manufacturer=manufacturer,
        )

    assert result is created
    assert manager_create.call_args.kwargs["manufacturer"] is manufacturer
    assert manager_create.call_args.kwargs["role"] == expected_role
    assert manager_create.call_args.kwargs["last_seen"] is not None


def test_create_chassis_canonicalizes_mac_at_persistence_boundary() -> None:
    """Direct service callers cannot persist vendor-specific MAC formatting."""
    manager_create = Mock(return_value=object())
    payload = _payload()
    payload.mac_address = "AA-BB-CC-DD-EE-FF"
    with patch(
        "micboard.models.hardware.wireless_chassis.WirelessChassis.objects.create",
        manager_create,
    ):
        WirelessChassisPersistenceService.create_from_normalized(
            payload=payload,
            manufacturer=object(),
        )

    assert manager_create.call_args.kwargs["mac_address"] == "aa:bb:cc:dd:ee:ff"
