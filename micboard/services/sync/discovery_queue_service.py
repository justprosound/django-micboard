"""Normalize manufacturer payloads and persist discovery review entries."""

from __future__ import annotations

import ipaddress
import logging
import re
from itertools import islice
from typing import Any

from pydantic import ValidationError

from micboard.discovery.limits import (
    MAX_DISCOVERY_CANDIDATES,
    MAX_DISCOVERY_METADATA_DEPTH,
    MAX_DISCOVERY_METADATA_FIELDS,
    MAX_DISCOVERY_METADATA_LIST_ITEMS,
    MAX_DISCOVERY_METADATA_STRING_LENGTH,
)
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.queue import DiscoveryQueue
from micboard.services.common.base.plugin import ManufacturerPlugin
from micboard.services.common.base.utils import validate_hostname
from micboard.services.manufacturer.secret_redaction import REDACTED_VALUE, is_secret_key
from micboard.services.sync.discovery_dtos import DiscoveryQueueDevice, DiscoverySyncSummary

logger = logging.getLogger(__name__)

INCOMPLETE_VENDOR_PAYLOAD_REASON = "vendor_device_payload_incomplete"


class DiscoveryQueueService:
    """Convert vendor device payloads into reviewable discovery queue entries."""

    @staticmethod
    def _bounded_log_identity(value: object) -> str:
        """Return a control-character-free identity suitable for structured logs."""
        identity = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "unidentified")).strip()
        return identity[:64] or "unidentified"

    @classmethod
    def _bound_metadata(cls, value: Any, *, depth: int = 0) -> Any:
        """Return a JSON-compatible, depth/width/string-bounded payload copy."""
        if depth >= MAX_DISCOVERY_METADATA_DEPTH:
            return "<truncated>"
        if isinstance(value, dict):
            items = list(islice(value.items(), MAX_DISCOVERY_METADATA_FIELDS + 1))
            bounded = {
                str(key)[:MAX_DISCOVERY_METADATA_STRING_LENGTH]: REDACTED_VALUE
                if is_secret_key(key)
                else cls._bound_metadata(item, depth=depth + 1)
                for key, item in items[:MAX_DISCOVERY_METADATA_FIELDS]
            }
            if len(items) > MAX_DISCOVERY_METADATA_FIELDS:
                bounded["_truncated"] = True
            return bounded
        if isinstance(value, (list, tuple)):
            items = list(islice(value, MAX_DISCOVERY_METADATA_LIST_ITEMS + 1))
            bounded_items = [
                cls._bound_metadata(item, depth=depth + 1)
                for item in items[:MAX_DISCOVERY_METADATA_LIST_ITEMS]
            ]
            if len(items) > MAX_DISCOVERY_METADATA_LIST_ITEMS:
                bounded_items.append("<truncated>")
            return bounded_items
        if isinstance(value, str):
            return value[:MAX_DISCOVERY_METADATA_STRING_LENGTH]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)[:MAX_DISCOVERY_METADATA_STRING_LENGTH]

    @staticmethod
    def humanize_fqdn(fqdn: str) -> str:
        """Convert the first hostname label into a readable device name."""
        label = fqdn.split(".")[0]
        label = re.sub(r"[_-]+", " ", label)
        label = re.sub(r"(wm)(\d*)$", r" WM\2", label, flags=re.IGNORECASE)
        label = re.sub(r"([a-zA-Z])([0-9])", r"\1 \2", label)
        words = re.sub(r"\s+", " ", label).strip().split(" ")
        return " ".join("WM" if word.casefold() == "wm" else word.capitalize() for word in words)

    @staticmethod
    def classify_device_type(model: str, raw_type: str) -> str:
        """Map vendor-specific device labels onto supported queue roles."""
        normalized_type = raw_type.casefold()
        if "SBC" in model.upper() or "charger" in normalized_type:
            return "charger"
        if "transmitter" in normalized_type:
            return "transmitter"
        if "transceiver" in normalized_type:
            return "transceiver"
        return "receiver"

    @classmethod
    def normalize_device(cls, device: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize one vendor payload without mutating the caller's data."""
        device_id = device.get("id") or device.get("api_device_id") or device.get("deviceId")
        serial = device.get("serial") or device.get("serialNumber")
        ip_address = device.get("ip") or device.get("ipAddress") or device.get("ipv4")
        model = device.get("model") or device.get("deviceType") or ""
        name = device.get("name") or model
        if not serial or not ip_address:
            missing_fields = [
                field_name
                for field_name, field_value in (
                    ("serial", serial),
                    ("ip", ip_address),
                )
                if not field_value
            ]
            logger.warning(
                "Skipping discovery device %r; missing required fields: %s",
                cls._bounded_log_identity(device_id),
                ",".join(missing_fields),
            )
            return None

        try:
            ip_text = str(ipaddress.ip_address(str(ip_address)))
        except ValueError:
            logger.warning(
                "Skipping discovery device %r; invalid IP address",
                cls._bounded_log_identity(device_id),
            )
            return None
        fqdn_candidate = str(device.get("fqdn") or "").strip().rstrip(".").lower()
        fqdn = (
            fqdn_candidate
            if len(fqdn_candidate) <= 255 and validate_hostname(fqdn_candidate)
            else ""
        )
        metadata = cls._bound_metadata(device)
        if fqdn:
            metadata.setdefault("fqdn", fqdn)
            if not name or name in (model, ip_address, ip_text):
                name = cls.humanize_fqdn(fqdn)

        firmware = (
            device.get("firmware")
            or device.get("firmware_version")
            or device.get("firmwareVersion")
            or ""
        )
        try:
            normalized = DiscoveryQueueDevice(
                api_device_id=str(device_id or ""),
                device_type=cls.classify_device_type(
                    str(model),
                    str(device.get("type", "UNKNOWN")),
                ),
                firmware_version=str(firmware)[:50],
                fqdn=fqdn,
                ip=ip_text,
                metadata=metadata,
                model=str(model)[:50],
                name=str(name)[:100],
                serial_number=str(serial),
            )
        except ValidationError:
            logger.warning(
                "Skipping discovery device %r; identifier exceeded storage constraints",
                cls._bounded_log_identity(device_id),
            )
            return None
        return normalized.model_dump()

    @staticmethod
    def upsert(
        manufacturer: Manufacturer,
        device_data: dict[str, Any],
        summary: DiscoverySyncSummary,
    ) -> None:
        """Upsert a queue item and refresh its duplicate-conflict snapshot."""
        defaults = dict(device_data)
        serial_number = str(defaults.pop("serial_number"))
        for workflow_field in ("status", "reviewed_at", "reviewed_by", "reviewed_by_id"):
            defaults.pop(workflow_field, None)
        queue_entry, created = DiscoveryQueue.objects.update_or_create(
            manufacturer=manufacturer,
            serial_number=serial_number,
            defaults=defaults,
        )
        from micboard.services.deduplication.queue_conflict_service import (
            DiscoveryQueueConflictService,
        )

        conflicts = DiscoveryQueueConflictService.check(queue_entry)
        queue_entry.is_duplicate = conflicts.is_duplicate
        queue_entry.is_ip_conflict = conflicts.is_ip_conflict
        queue_entry.existing_device = conflicts.existing_device
        queue_entry.existing_charger = conflicts.existing_charger
        update_fields = [
            "is_duplicate",
            "is_ip_conflict",
            "existing_device",
            "existing_charger",
        ]
        if queue_entry.status == "pending":
            queue_entry.reviewed_at = None
            queue_entry.reviewed_by_id = None
            update_fields.extend(("reviewed_at", "reviewed_by"))
        queue_entry.save(
            update_fields=update_fields,
        )
        if created:
            summary.created_receivers += 1

    @classmethod
    def poll_and_persist(
        cls,
        manufacturer: Manufacturer,
        plugin: ManufacturerPlugin,
        summary: DiscoverySyncSummary,
    ) -> None:
        """Poll a plugin and stage each usable device for review."""
        raw_devices = plugin.get_devices() or []
        devices = list(islice(iter(raw_devices), MAX_DISCOVERY_CANDIDATES + 1))
        payload_incomplete = len(devices) > MAX_DISCOVERY_CANDIDATES or any(
            not isinstance(device, dict) for device in devices
        )
        devices = [
            device for device in devices[:MAX_DISCOVERY_CANDIDATES] if isinstance(device, dict)
        ]
        if payload_incomplete:
            summary.record_error(INCOMPLETE_VENDOR_PAYLOAD_REASON)
            logger.warning("Vendor device payload was invalid or exceeded the hard limit")
        if not devices:
            logger.info("No devices returned from API")
            return

        for device in devices:
            device_data = cls.normalize_device(device)
            if device_data is not None:
                cls.upsert(manufacturer, device_data, summary)
