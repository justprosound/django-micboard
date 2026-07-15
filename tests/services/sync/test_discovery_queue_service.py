from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest

from micboard.discovery.limits import (
    MAX_DISCOVERY_CANDIDATES,
    MAX_DISCOVERY_METADATA_DEPTH,
    MAX_DISCOVERY_METADATA_FIELDS,
    MAX_DISCOVERY_METADATA_LIST_ITEMS,
    MAX_DISCOVERY_METADATA_STRING_LENGTH,
)
from micboard.services.manufacturer.secret_redaction import REDACTED_VALUE
from micboard.services.sync.discovery_dtos import DiscoverySyncSummary
from micboard.services.sync.discovery_queue_service import (
    INCOMPLETE_VENDOR_PAYLOAD_REASON,
    DiscoveryQueueService,
)
from tests.factories.base import UserFactory
from tests.factories.discovery import DiscoveryQueueFactory, ManufacturerFactory


@pytest.mark.parametrize(
    ("fqdn", "expected"),
    [
        ("lecture_hall-wm2.example.test", "Lecture Hall WM 2"),
        ("receiver12.example.test", "Receiver 12"),
        ("wm.example.test", "WM"),
    ],
)
def test_humanize_fqdn(fqdn: str, expected: str) -> None:
    assert DiscoveryQueueService.humanize_fqdn(fqdn) == expected


@pytest.mark.parametrize(
    ("model", "raw_type", "expected"),
    [
        ("SBC250", "unknown", "charger"),
        ("CHG-1", "rack charger", "charger"),
        ("SKM", "handheld transmitter", "transmitter"),
        ("ANX4", "transceiver", "transceiver"),
        ("ULXD4Q", "unknown", "receiver"),
    ],
)
def test_classify_device_type(model: str, raw_type: str, expected: str) -> None:
    assert DiscoveryQueueService.classify_device_type(model, raw_type) == expected


@pytest.mark.parametrize(
    "device",
    [
        {"ip": "192.0.2.20"},
        {"serial": "serial-20"},
    ],
)
def test_normalize_device_rejects_payloads_without_identity_or_address(
    device: dict[str, str],
) -> None:
    assert DiscoveryQueueService.normalize_device(device) is None


def test_normalize_device_logs_only_bounded_identity_and_missing_fields(caplog) -> None:
    secret = "vendor-token-SENTINEL"
    device = {
        "id": f"receiver-24\nforged-line{'x' * 100}",
        "ip": "192.0.2.24",
        "token": secret,
    }

    assert DiscoveryQueueService.normalize_device(device) is None

    assert len(caplog.messages) == 1
    message = caplog.messages[0]
    assert secret not in message
    assert "\n" not in message
    assert "missing required fields: serial" in message
    assert "x" * 65 not in message


def test_normalize_device_rejects_malformed_ip_without_log_injection(caplog) -> None:
    device = {
        "id": "receiver-unsafe",
        "serial": "serial-unsafe",
        "ip": "not-an-ip\nforged-entry",
    }

    assert DiscoveryQueueService.normalize_device(device) is None

    assert len(caplog.messages) == 1
    assert "forged-entry" not in caplog.messages[0]
    assert "invalid IP address" in caplog.messages[0]


def test_normalize_device_redacts_and_bounds_nested_metadata() -> None:
    device = {
        "id": "receiver-secret",
        "serial": "serial-secret",
        "ip": "192.0.2.29",
        "nested": {
            "shared_key": "shared-secret-sentinel",
            "token": "token-secret-sentinel",
        },
        "large": "x" * (MAX_DISCOVERY_METADATA_STRING_LENGTH + 1),
        **{f"field-{index}": index for index in range(MAX_DISCOVERY_METADATA_FIELDS + 1)},
    }

    normalized = DiscoveryQueueService.normalize_device(device)

    assert normalized is not None
    metadata = normalized["metadata"]
    assert metadata["nested"] == {
        "shared_key": REDACTED_VALUE,
        "token": REDACTED_VALUE,
    }
    assert len(metadata["large"]) == MAX_DISCOVERY_METADATA_STRING_LENGTH
    assert metadata["_truncated"] is True
    assert "shared-secret-sentinel" not in str(metadata)
    assert "token-secret-sentinel" not in str(metadata)


def test_normalize_device_detects_secrets_before_key_truncation() -> None:
    """Long and camel-case secret keys cannot evade bounded metadata redaction."""
    long_key = "x" * MAX_DISCOVERY_METADATA_STRING_LENGTH + "_apiToken"
    sentinel = "PRIVATE-METADATA-SENTINEL"
    device = {
        "id": "receiver-long-secret",
        "serial": "serial-long-secret",
        "ip": "192.0.2.39",
        long_key: sentinel,
        "nested": {"privateKey": sentinel},
    }

    normalized = DiscoveryQueueService.normalize_device(device)

    assert normalized is not None
    metadata = normalized["metadata"]
    assert metadata[long_key[:MAX_DISCOVERY_METADATA_STRING_LENGTH]] == REDACTED_VALUE
    assert metadata["nested"]["privateKey"] == REDACTED_VALUE
    assert sentinel not in str(metadata)


def test_normalize_device_bounds_nested_lists_and_depth() -> None:
    """Secret-safe traversal retains its list and recursion resource ceilings."""
    nested: object = "leaf"
    for _ in range(MAX_DISCOVERY_METADATA_DEPTH + 1):
        nested = {"next": nested}
    device = {
        "id": "receiver-bounded-nesting",
        "serial": "serial-bounded-nesting",
        "ip": "192.0.2.40",
        "items": list(range(MAX_DISCOVERY_METADATA_LIST_ITEMS + 1)),
        "nested": nested,
    }

    normalized = DiscoveryQueueService.normalize_device(device)

    assert normalized is not None
    metadata = normalized["metadata"]
    assert metadata["items"][-1] == "<truncated>"
    assert "<truncated>" in str(metadata["nested"])


def test_normalize_device_rejects_oversized_identifiers_and_bounds_display_fields() -> None:
    oversized_identifier = {
        "id": "receiver",
        "serial": "s" * 101,
        "ip": "192.0.2.30",
    }
    assert DiscoveryQueueService.normalize_device(oversized_identifier) is None

    normalized = DiscoveryQueueService.normalize_device(
        {
            "id": "receiver",
            "serial": "serial",
            "ip": "192.0.2.31",
            "model": "m" * 60,
            "name": "n" * 110,
            "firmware": "f" * 60,
        }
    )

    assert normalized is not None
    assert len(normalized["model"]) == 50
    assert len(normalized["name"]) == 100
    assert len(normalized["firmware_version"]) == 50


def test_normalize_device_preserves_payload_and_uses_vendor_fallback_fields() -> None:
    device = {
        "deviceId": "api-21",
        "serialNumber": "serial-21",
        "ipv4": "192.0.2.21",
        "deviceType": "EW-DX",
        "type": "transceiver",
        "firmwareVersion": "1.2.3",
    }
    original = deepcopy(device)

    normalized = DiscoveryQueueService.normalize_device(device)

    assert normalized == {
        "api_device_id": "api-21",
        "device_type": "transceiver",
        "firmware_version": "1.2.3",
        "fqdn": "",
        "ip": "192.0.2.21",
        "metadata": original,
        "model": "EW-DX",
        "name": "EW-DX",
        "serial_number": "serial-21",
    }
    assert device == original


def test_normalize_device_uses_validated_hostname_for_vendor_default_name() -> None:
    device = {
        "id": 22,
        "serial": 2200,
        "ipAddress": "192.0.2.22",
        "model": "ULXD4Q",
        "name": "ULXD4Q",
        "firmware_version": "2.0",
        "fqdn": "lecture-wm1.example.test",
    }
    with patch.object(
        DiscoveryQueueService,
        "humanize_fqdn",
        return_value="Lecture WM 1",
    ) as humanize:
        normalized = DiscoveryQueueService.normalize_device(device)

    assert normalized is not None
    assert normalized["name"] == "Lecture WM 1"
    assert normalized["metadata"]["fqdn"] == "lecture-wm1.example.test"
    humanize.assert_called_once_with("lecture-wm1.example.test")


def test_normalize_device_keeps_explicit_name_and_existing_dns_metadata() -> None:
    device = {
        "api_device_id": "api-23",
        "serial": "serial-23",
        "ip": "192.0.2.23",
        "name": "Front Rack",
        "model": "ULXD4D",
        "firmware": "3.0",
        "fqdn": "vendor-name.example.test",
        "ptr_validated": False,
    }
    with patch.object(DiscoveryQueueService, "humanize_fqdn") as humanize:
        normalized = DiscoveryQueueService.normalize_device(device)

    assert normalized is not None
    assert normalized["name"] == "Front Rack"
    assert normalized["metadata"]["fqdn"] == "vendor-name.example.test"
    assert normalized["metadata"]["ptr_validated"] is False
    humanize.assert_not_called()


@pytest.mark.parametrize("created", [True, False])
def test_upsert_refreshes_conflict_snapshot_without_mutating_input(created: bool) -> None:
    queue_entry = SimpleNamespace(
        is_duplicate=False,
        is_ip_conflict=False,
        existing_device=None,
        existing_charger=None,
        reviewed_at=None,
        reviewed_by_id=None,
        status="pending",
        save=Mock(),
    )
    device_data = {"serial_number": "serial-24", "ip": "192.0.2.24"}
    summary = DiscoverySyncSummary(manufacturer=1)
    manager_path = (
        "micboard.services.sync.discovery_queue_service.DiscoveryQueue.objects.update_or_create"
    )

    conflicts = SimpleNamespace(
        is_duplicate=True,
        is_ip_conflict=True,
        existing_device="chassis",
        existing_charger="charger",
    )
    with (
        patch(manager_path, return_value=(queue_entry, created)) as update_or_create,
        patch(
            "micboard.services.deduplication.queue_conflict_service."
            "DiscoveryQueueConflictService.check",
            return_value=conflicts,
        ),
    ):
        DiscoveryQueueService.upsert(SimpleNamespace(), device_data, summary)

    update_or_create.assert_called_once_with(
        manufacturer=update_or_create.call_args.kwargs["manufacturer"],
        serial_number="serial-24",
        defaults={"ip": "192.0.2.24"},
    )
    assert device_data == {"serial_number": "serial-24", "ip": "192.0.2.24"}
    assert summary.created_receivers == int(created)
    assert queue_entry.is_duplicate is True
    assert queue_entry.is_ip_conflict is True
    assert queue_entry.existing_device == "chassis"
    assert queue_entry.existing_charger == "charger"
    queue_entry.save.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["approved", "rejected", "imported", "duplicate"])
def test_rediscovery_preserves_reviewed_workflow_state(status: str) -> None:
    reviewer = UserFactory()
    reviewed_at = timezone.now()
    queue_entry = DiscoveryQueueFactory(
        status=status,
        serial_number=f"reviewed-{status}",
        reviewed_at=reviewed_at,
        reviewed_by=reviewer,
        name="Old name",
    )
    summary = DiscoverySyncSummary(manufacturer=queue_entry.manufacturer_id)

    DiscoveryQueueService.upsert(
        queue_entry.manufacturer,
        {
            "serial_number": queue_entry.serial_number,
            "name": "Refreshed name",
            "status": "pending",
            "reviewed_at": None,
            "reviewed_by": None,
        },
        summary,
    )

    queue_entry.refresh_from_db()
    assert queue_entry.name == "Refreshed name"
    assert queue_entry.status == status
    assert queue_entry.reviewed_at == reviewed_at
    assert queue_entry.reviewed_by == reviewer
    assert summary.created_receivers == 0


@pytest.mark.django_db
def test_rediscovery_clears_review_metadata_from_pending_entry() -> None:
    reviewer = UserFactory()
    queue_entry = DiscoveryQueueFactory(
        status="pending",
        serial_number="pending-with-stale-review",
        reviewed_at=timezone.now(),
        reviewed_by=reviewer,
    )
    summary = DiscoverySyncSummary(manufacturer=queue_entry.manufacturer_id)

    DiscoveryQueueService.upsert(
        queue_entry.manufacturer,
        {
            "serial_number": queue_entry.serial_number,
            "ip": "192.0.2.25",
        },
        summary,
    )

    queue_entry.refresh_from_db()
    assert queue_entry.status == "pending"
    assert queue_entry.reviewed_at is None
    assert queue_entry.reviewed_by is None


@pytest.mark.django_db
def test_new_discovery_uses_pending_workflow_defaults() -> None:
    manufacturer = ManufacturerFactory()
    reviewer = UserFactory()
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk)

    DiscoveryQueueService.upsert(
        manufacturer,
        {
            "api_device_id": "new-api-device",
            "device_type": "receiver",
            "ip": "192.0.2.26",
            "serial_number": "new-serial",
            "status": "imported",
            "reviewed_at": timezone.now(),
            "reviewed_by": reviewer,
        },
        summary,
    )

    queue_entry = manufacturer.discoveryqueue_set.get(serial_number="new-serial")
    assert queue_entry.status == "pending"
    assert queue_entry.reviewed_at is None
    assert queue_entry.reviewed_by is None
    assert summary.created_receivers == 1


def test_poll_and_persist_handles_empty_and_mixed_payloads() -> None:
    summary = DiscoverySyncSummary(manufacturer=1)
    empty_plugin = SimpleNamespace(get_devices=Mock(return_value=None))
    assert DiscoveryQueueService.poll_and_persist(SimpleNamespace(), empty_plugin, summary) is None

    devices = [{"id": "valid"}, {"id": "invalid"}]
    plugin = SimpleNamespace(get_devices=Mock(return_value=devices))
    normalized = {"serial_number": "serial", "ip": "192.0.2.25"}
    with (
        patch.object(
            DiscoveryQueueService,
            "normalize_device",
            side_effect=[normalized, None],
        ),
        patch.object(DiscoveryQueueService, "upsert") as upsert,
    ):
        assert DiscoveryQueueService.poll_and_persist(SimpleNamespace(), plugin, summary) is None

    upsert.assert_called_once_with(
        upsert.call_args.args[0],
        normalized,
        summary,
    )


def test_poll_and_persist_bounds_raw_vendor_iterable_and_marks_incomplete() -> None:
    summary = DiscoverySyncSummary(manufacturer=1)
    consumed = 0

    def devices():
        nonlocal consumed
        for index in range(MAX_DISCOVERY_CANDIDATES + 2):
            consumed += 1
            yield {"id": index}

    plugin = SimpleNamespace(get_devices=Mock(return_value=devices()))
    with (
        patch.object(DiscoveryQueueService, "normalize_device", return_value=None),
        patch.object(DiscoveryQueueService, "upsert") as upsert,
    ):
        DiscoveryQueueService.poll_and_persist(
            SimpleNamespace(),
            plugin,
            summary,
        )

    assert consumed == MAX_DISCOVERY_CANDIDATES + 1
    assert summary.errors == [INCOMPLETE_VENDOR_PAYLOAD_REASON]
    upsert.assert_not_called()
