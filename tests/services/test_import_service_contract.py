"""Device import normalization and server isolation contracts."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import Mock, call

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Location
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager
from micboard.services.deduplication.identity_mutation_lock import (
    DeviceIdentityMutationLockService,
)
from micboard.services.deduplication.result import DeduplicationResult
from micboard.services.import_service import ImportService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.factories.locations import LocationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "device", "ip": "192.0.2.180"},
        {"id": "device", "serial": "serial"},
        {"ip": "192.0.2.180", "serial": "serial"},
        {"id": None, "ip": "192.0.2.180", "serial": "serial"},
    ],
)
def test_import_rejects_incomplete_identity(payload: dict) -> None:
    """Serial, address, and external ID are mandatory persistence keys."""
    assert ImportService().import_device(payload, ManufacturerFactory()) == (False, False)


def test_dry_run_distinguishes_create_and_update_without_writes() -> None:
    """Dry-run results describe the action without mutating inventory."""
    manufacturer = ManufacturerFactory()
    existing = WirelessChassisFactory(manufacturer=manufacturer, serial_number="existing")
    service = ImportService()

    assert service.import_device(
        {"serial": existing.serial_number, "ip": existing.ip, "id": "existing"},
        manufacturer,
        dry_run=True,
    ) == (False, True)
    assert service.import_device(
        {"serial": "new", "ip": "192.0.2.181", "id": "new"},
        manufacturer,
        dry_run=True,
    ) == (True, False)
    assert manufacturer.wirelesschassis_set.count() == 1


def test_import_creates_and_updates_normalized_alias_payload() -> None:
    """Snake and camel aliases converge on one chassis with valid lifecycle state."""
    manufacturer = ManufacturerFactory()
    location = LocationFactory()
    service = ImportService()

    assert service.import_device(
        {
            "serial": "serial-182",
            "model": "TX-1",
            "ip": "192.0.2.182",
            "mac": "00:11:22:33:44:66",
            "id": "device-182",
            "type": "IEM transmitter",
            "state": "ONLINE",
        },
        manufacturer,
        location,
    ) == (True, False)

    chassis = manufacturer.wirelesschassis_set.get(serial_number="serial-182")
    assert chassis.role == "transmitter"
    assert chassis.status == "online"
    assert chassis.is_online is True
    assert chassis.location == location
    assert chassis.mac_address == "00:11:22:33:44:66"

    assert service.import_device(
        {
            "serialNumber": "serial-182",
            "deviceType": "Hybrid Base",
            "ipAddress": "192.0.2.183",
            "macAddress": "00:11:22:33:44:77",
            "deviceId": "device-182",
            "type": "transceiver",
            "state": "OFFLINE",
        },
        manufacturer,
    ) == (False, True)

    chassis.refresh_from_db()
    assert chassis.role == "transceiver"
    assert chassis.status == "offline"
    assert chassis.is_online is False
    assert str(chassis.ip) == "192.0.2.183"
    assert chassis.mac_address == "00:11:22:33:44:77"


def test_import_canonicalizes_valid_mac_and_discards_invalid_placeholder() -> None:
    """Only canonical hardware addresses cross the import persistence boundary."""
    manufacturer = ManufacturerFactory()
    service = ImportService()

    assert service.import_device(
        {
            "serial": "canonical-mac",
            "ip": "192.0.2.184",
            "id": "canonical-mac",
            "mac": "AA-BB-CC-DD-EE-FF",
        },
        manufacturer,
    ) == (True, False)
    assert service.import_device(
        {
            "serial": "placeholder-mac",
            "ip": "192.0.2.185",
            "id": "placeholder-mac",
            "mac": "unknown-device",
        },
        manufacturer,
    ) == (True, False)

    canonical = manufacturer.wirelesschassis_set.get(serial_number="canonical-mac")
    placeholder = manufacturer.wirelesschassis_set.get(serial_number="placeholder-mac")
    assert canonical.mac_address == "aa:bb:cc:dd:ee:ff"
    assert placeholder.mac_address is None


@pytest.mark.parametrize(
    ("device_type", "expected_role"),
    [("receiver", "receiver"), (object(), "receiver")],
)
def test_import_defaults_unknown_model_role_and_state(
    device_type: object,
    expected_role: str,
) -> None:
    """Unrecognized optional metadata receives valid conservative model defaults."""
    manufacturer = ManufacturerFactory()
    serial = f"serial-{manufacturer.pk}"

    assert ImportService().import_device(
        {
            "serial": serial,
            "ip": f"192.0.2.{190 + manufacturer.pk}",
            "id": serial,
            "type": device_type,
        },
        manufacturer,
    ) == (True, False)

    chassis = manufacturer.wirelesschassis_set.get(serial_number=serial)
    assert chassis.model == "Unknown"
    assert chassis.role == expected_role
    assert chassis.status == "discovered"


def test_import_skips_lifecycle_write_when_status_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata-only refreshes avoid redundant lifecycle and audit writes."""
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="same-state",
        status="discovered",
    )
    lifecycle_factory = Mock()
    monkeypatch.setattr(
        "micboard.services.import_service.HardwareLifecycleManager",
        lifecycle_factory,
    )

    assert ImportService().import_device(
        {
            "serial": chassis.serial_number,
            "ip": chassis.ip,
            "id": chassis.api_device_id,
            "model": "Updated Model",
        },
        manufacturer,
    ) == (False, True)

    lifecycle_factory.assert_not_called()
    chassis.refresh_from_db()
    assert chassis.model == "Updated Model"


def test_import_reconciles_discovered_device_through_provisioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Online imports traverse the required provisioning lifecycle state."""
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="newly-online",
        status="discovered",
    )
    lifecycle = HardwareLifecycleManager()
    manager = Mock()
    manager.transition_device.side_effect = lifecycle.transition_device
    lifecycle_factory = Mock(return_value=manager)
    monkeypatch.setattr(
        "micboard.services.import_service.HardwareLifecycleManager",
        lifecycle_factory,
    )

    assert ImportService().import_device(
        {
            "serial": chassis.serial_number,
            "ip": "192.0.2.198",
            "id": "newly-online-api-id",
            "state": "ONLINE",
        },
        manufacturer,
        server_id="primary",
    ) == (False, True)

    transition_arguments = {
        "reason": "Device state received during import",
        "metadata": {
            "source": "import",
            "server_id": "primary",
            "target_status": "online",
        },
    }
    assert manager.transition_device.call_args_list == [
        call(chassis, "provisioning", **transition_arguments),
        call(chassis, "online", **transition_arguments),
    ]
    lifecycle_factory.assert_called_once_with()
    chassis.refresh_from_db()
    assert chassis.status == "online"
    assert chassis.is_online is True
    assert str(chassis.ip) == "192.0.2.198"


def test_import_rolls_back_when_lifecycle_rejects_a_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected lifecycle hop cannot leave partial metadata or state writes."""
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="rejected-online",
        model="Original Model",
        status="discovered",
    )
    lifecycle = HardwareLifecycleManager()
    manager = Mock()

    def reject_online(device, to_status: str, **kwargs) -> bool:
        if to_status == "online":
            return False
        return lifecycle.transition_device(device, to_status, **kwargs)

    manager.transition_device.side_effect = reject_online
    monkeypatch.setattr(
        "micboard.services.import_service.HardwareLifecycleManager",
        Mock(return_value=manager),
    )

    with pytest.raises(RuntimeError, match="rejected imported status transition to 'online'"):
        ImportService().import_device(
            {
                "serial": chassis.serial_number,
                "model": "Uncommitted Model",
                "ip": "192.0.2.199",
                "id": "uncommitted-api-id",
                "state": "ONLINE",
            },
            manufacturer,
            server_id="primary",
        )

    chassis.refresh_from_db()
    assert chassis.status == "discovered"
    assert chassis.model == "Original Model"
    assert str(chassis.ip) != "192.0.2.199"
    assert chassis.api_device_id != "uncommitted-api-id"


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("identity_field", ["serial", "mac", "ip"])
def test_import_rejects_cross_vendor_durable_identity(
    identity_field: str,
    dry_run: bool,
) -> None:
    """Serial, canonical MAC, and occupied IP ownership fail closed across vendors."""
    first = ManufacturerFactory()
    second = ManufacturerFactory()
    foreign = WirelessChassisFactory(
        manufacturer=first,
        serial_number="shared-serial" if identity_field == "serial" else "foreign-serial",
        mac_address="aa:bb:cc:dd:ee:ff" if identity_field == "mac" else None,
        ip="192.0.2.195",
    )
    payload = {
        "serial": "shared-serial" if identity_field == "serial" else "incoming-serial",
        "ip": "192.0.2.196",
        "id": "second-device",
    }
    if identity_field == "mac":
        payload["mac"] = "AA-BB-CC-DD-EE-FF"
    elif identity_field == "ip":
        payload["ip"] = "192.0.2.195"

    assert ImportService().import_device(payload, second, dry_run=dry_run) == (False, False)
    assert first.wirelesschassis_set.count() == 1
    assert second.wirelesschassis_set.count() == 0
    foreign.refresh_from_db()
    assert str(foreign.ip) == "192.0.2.195"


def test_import_checks_identity_inside_shared_lock_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Imports classify and persist only while holding the global identity lock."""
    manufacturer = ManufacturerFactory()
    events: list[str] = []

    @contextmanager
    def acquire(*, manufacturer):
        events.append("locked")
        yield manufacturer
        events.append("released")

    def classify(**_kwargs: object) -> DeduplicationResult:
        assert events == ["locked"]
        events.append("checked")
        return DeduplicationResult.new()

    def create(**_kwargs: object) -> object:
        assert events == ["locked", "checked"]
        events.append("written")
        return object()

    monkeypatch.setattr(DeviceIdentityMutationLockService, "acquire", acquire)
    monkeypatch.setattr("micboard.services.import_service.check_device", classify)
    monkeypatch.setattr(WirelessChassis.objects, "create", create)

    assert ImportService().import_device(
        {
            "serial": "ordered-import",
            "ip": "192.0.2.197",
            "id": "ordered-import",
        },
        manufacturer,
    ) == (True, False)
    assert events == ["locked", "checked", "written", "released"]


def test_import_rejects_foreign_row_if_deduplication_misclassifies_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The import persistence boundary independently enforces manufacturer ownership."""
    incoming_manufacturer = ManufacturerFactory()
    foreign = WirelessChassisFactory(
        manufacturer=ManufacturerFactory(),
        serial_number="defense-foreign-serial",
        ip="192.0.2.214",
    )
    monkeypatch.setattr(
        "micboard.services.import_service.check_device",
        Mock(return_value=DeduplicationResult.duplicate(foreign)),
    )

    assert ImportService().import_device(
        {
            "serial": "defense-incoming-serial",
            "ip": "192.0.2.215",
            "id": "defense-incoming-device",
        },
        incoming_manufacturer,
    ) == (False, False)
    foreign.refresh_from_db()
    assert foreign.serial_number == "defense-foreign-serial"
    assert str(foreign.ip) == "192.0.2.214"


def test_server_import_resolves_locations_and_counts_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server totals include discoveries, creates, and updates across location outcomes."""
    service = ImportService()
    manufacturer = ManufacturerFactory()
    location = LocationFactory()
    fetch = Mock(side_effect=[[{"id": "one"}, {"id": "two"}], [{"id": "three"}]])
    monkeypatch.setattr(
        "micboard.services.integrations.api_server_service."
        "APIServerConnectionService.fetch_shure_devices",
        fetch,
    )
    location_lookup = Mock(side_effect=[location, Location.DoesNotExist])
    monkeypatch.setattr(Location.objects, "get", location_lookup)
    import_device = Mock(side_effect=[(True, False), (False, True), (True, False)])
    monkeypatch.setattr(service, "import_device", import_device)
    servers = {
        "one": {
            "base_url": "https://one.example.test",
            "shared_key": "one-secret",
            "location_id": 1,
        },
        "two": {
            "manufacturer": "SHURE",
            "base_url": "https://two.example.test",
            "shared_key": "two-secret",
            "location_id": 999,
        },
    }

    assert service.import_from_servers(
        servers,
        manufacturer,
        {"dry_run": True, "full": True},
    ) == (3, 2, 1)
    assert import_device.call_args_list == [
        call(
            device={"id": "one"},
            manufacturer=manufacturer,
            location=location,
            server_id="one",
            dry_run=True,
            full=True,
        ),
        call(
            device={"id": "two"},
            manufacturer=manufacturer,
            location=location,
            server_id="one",
            dry_run=True,
            full=True,
        ),
        call(
            device={"id": "three"},
            manufacturer=manufacturer,
            location=None,
            server_id="two",
            dry_run=True,
            full=True,
        ),
    ]


def test_server_import_handles_empty_inventory_and_per_device_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One malformed device cannot discard other server results."""
    service = ImportService()
    manufacturer = ManufacturerFactory()
    fetch = Mock(side_effect=[None, [{"id": "bad"}, {"id": "good"}]])
    monkeypatch.setattr(
        "micboard.services.integrations.api_server_service."
        "APIServerConnectionService.fetch_shure_devices",
        fetch,
    )
    import_device = Mock(side_effect=[RuntimeError("bad payload"), (False, True)])
    monkeypatch.setattr(service, "import_device", import_device)
    servers = {
        name: {
            "manufacturer": "shure",
            "base_url": f"https://{name}.example.test",
            "shared_key": f"{name}-secret",
        }
        for name in ("empty", "mixed")
    }

    assert service.import_from_servers(servers, manufacturer, {}) == (2, 0, 1)
