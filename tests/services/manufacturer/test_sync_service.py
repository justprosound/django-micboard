"""Manufacturer synchronization orchestration and persistence contracts."""

from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from django.db import connection
from django.test import override_settings

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.deduplication.check import check_device
from micboard.services.deduplication.identity_index import DeviceIdentityIndex
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.sync.polling_dtos import (
    DEFAULT_BROADCAST_CHUNK_SIZE,
    DEFAULT_MAX_POLL_DEVICES,
    HARD_MAX_POLL_DEVICES,
    ManufacturerPollLimits,
    ManufacturerSyncResult,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _payload(**overrides: object) -> NormalizedChassis:
    values = {
        "api_device_id": "device-1",
        "ip": "192.0.2.100",
        "serial_number": "serial-1",
        "mac_address": "00:11:22:33:44:55",
        "name": "Receiver",
        "model": "RX-1",
        "role": "receiver",
        "firmware_version": "1.0",
        "hosted_firmware_version": "1.1",
        "description": "Rack receiver",
        "subnet_mask": "255.255.255.0",
        "gateway": "192.0.2.1",
        "network_mode": "static",
        "interface_id": "eth0",
    }
    values.update(overrides)
    return NormalizedChassis(**values)  # type: ignore[arg-type]


def _result(**overrides: object) -> ManufacturerSyncResult:
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
    return ManufacturerSyncResult(**values)  # type: ignore[arg-type]


def test_sync_reports_missing_manufacturer() -> None:
    """Unknown manufacturer codes fail before plugin discovery."""
    assert ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code="missing"
    ) == _result(success=False, errors=["Manufacturer not found or inactive: missing"])


def test_sync_reports_missing_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured manufacturers still require an installed integration."""
    ManufacturerFactory(code="vendor")
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(side_effect=ModuleNotFoundError("no integration for vendor")),
    )

    assert ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code="vendor"
    ).errors == ["Plugin not found: vendor"]


def test_sync_returns_zero_counts_for_empty_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful empty manufacturer response is not treated as a failure."""
    ManufacturerFactory(code="vendor")
    plugin = Mock()
    plugin.get_devices.return_value = None
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
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
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[_payload()]),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code=manufacturer.code,
    )

    assert result == _result(
        success=False,
        errors=["Manufacturer became inactive during polling; no devices were synchronized."],
        devices_examined=1,
    )
    assert not WirelessChassis.objects.exists()


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
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[_payload()]),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(
        manufacturer_code=manufacturer.code,
        force=True,
    )

    assert result == _result(devices_added=1, devices_examined=1)
    assert WirelessChassis.objects.filter(manufacturer=manufacturer).count() == 1


def test_sync_counts_created_and_updated_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only persisted create and update outcomes contribute to the summary."""
    manufacturer = ManufacturerFactory(code="vendor")
    other = ManufacturerFactory(code="other-vendor")
    WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="device-1",
        serial_number="serial-1",
        mac_address="00:11:22:33:44:55",
        ip="192.0.2.100",
    )
    WirelessChassisFactory(manufacturer=other, serial_number="foreign-serial", ip="192.0.2.199")
    plugin = Mock()
    plugin.get_devices.return_value = [{"id": "raw"}]
    payloads = [
        _payload(),
        _payload(
            api_device_id="device-2",
            serial_number="serial-2",
            mac_address="00:11:22:33:44:66",
            ip="192.0.2.101",
        ),
        _payload(
            api_device_id="device-3",
            serial_number="foreign-serial",
            mac_address="00:11:22:33:44:77",
            ip="192.0.2.102",
        ),
    ]
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(ManufacturerSyncService, "_normalize_devices", Mock(return_value=payloads))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert result == _result(devices_added=1, devices_updated=1, devices_examined=1)


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
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
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
    plugin.normalize_device.assert_not_called()


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
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
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
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
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
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert result.success is False
    assert result.errors == ["Device synchronization failed (TimeoutError); details redacted."]
    assert secret not in str(result)


def test_normalization_skips_unnormalizable_and_unaddressed_devices() -> None:
    """Only normalized devices with an address reach persistence."""
    plugin = Mock()
    complete = NormalizedChassis(api_device_id="complete", ip="192.0.2.110")
    plugin.normalize_device.side_effect = [
        None,
        NormalizedChassis(api_device_id="missing-address"),
        complete,
    ]

    result = ManufacturerSyncService._normalize_devices([{}, {}, {}], plugin)

    assert result == [complete]


@pytest.mark.parametrize(
    ("role", "expected_role"),
    [
        ("transmitter", "transmitter"),
        ("transceiver", "transceiver"),
        ("receiver", "receiver"),
        (None, "legacy"),
    ],
)
def test_update_existing_chassis_maps_role_and_preserves_blank_fields(
    role: str | None,
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
    payload = _payload(role=role).model_copy(
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
    ("role", "expected_role"),
    [("transmitter", "transmitter"), ("transceiver", "transceiver"), (None, "receiver")],
)
def test_create_chassis_maps_normalized_payload(
    role: str | None,
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
            payload=_payload(role=role),
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


def test_a_poll_that_deactivates_mid_run_still_records_its_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vendor I/O happened, so the failed poll has to leave a durable record behind it."""
    from micboard.models.audit.activity_log import ServiceSyncLog

    manufacturer = ManufacturerFactory(code="vendor")
    plugin = Mock()

    def deactivate_during_request() -> list[dict[str, str]]:
        type(manufacturer).objects.filter(pk=manufacturer.pk).update(is_active=False)
        return [{"id": "raw"}]

    plugin.get_devices.side_effect = deactivate_during_request
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[_payload()]),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert not result.success
    assert ServiceSyncLog.objects.filter(service=manufacturer).exists()


def test_a_plugin_that_fails_to_initialize_returns_a_failed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vendor constructor error is a poll outcome, not an exception for the caller."""
    ManufacturerFactory(code="vendor")
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(side_effect=RuntimeError("vendor client could not start")),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert not result.success
    assert result.errors
    assert "could not start" not in str(result.errors)


def test_a_plugin_initialization_failure_is_not_reported_as_a_missing_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfigured integration is a different operator problem from an absent one."""
    ManufacturerFactory(code="vendor")
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        Mock(side_effect=ValueError("SENNHEISER_API_PASSWORD is required")),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert not result.success
    assert result.errors != ["Plugin not found: vendor"]
