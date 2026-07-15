"""Identity resolution and conflict policy for discovery approval."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from django.core.exceptions import ValidationError

from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.services.sync.discovery_approval_inventory import LockedApprovalInventory


class ChassisApprovalTarget(PydanticBaseDTO):
    """Locked chassis target and the normalized identity to persist."""

    chassis: WirelessChassis | None
    api_device_id: str


class DiscoveryApprovalResolver:
    """Resolve locked inventory targets without allowing identity takeovers."""

    @staticmethod
    def text(value: Any) -> str:
        """Normalize optional discovery text without preserving whitespace-only values."""
        return str(value).strip() if value is not None else ""

    @classmethod
    def metadata_text(cls, item: DiscoveryQueue, *keys: str) -> str:
        """Read the first nonempty normalized metadata alias."""
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        for key in keys:
            value = cls.text(metadata.get(key))
            if value:
                return value
        return ""

    @classmethod
    def resolve_charger(
        cls,
        item: DiscoveryQueue,
        *,
        inventory: LockedApprovalInventory,
    ) -> Charger:
        """Resolve one explicit or unambiguous charger from pre-locked inventory."""
        if item.existing_charger_id is not None:
            charger = inventory.chargers_by_pk.get(item.existing_charger_id)
            if charger is None:
                raise ValidationError(
                    f"The charger linked to {item.name or item.ip} no longer exists."
                )
            if charger.manufacturer_id not in (None, item.manufacturer_id):
                raise ValidationError(
                    f"The charger linked to {item.name or item.ip} belongs to another manufacturer."
                )
            serial_number = cls.text(item.serial_number)
            existing_serial = cls.text(charger.serial_number)
            serial_matches = bool(
                serial_number and existing_serial and serial_number == existing_serial
            )
            if serial_number and not serial_matches:
                raise ValidationError(
                    f"The serial number for {item.name or item.ip} conflicts with existing inventory."
                )
            if item.is_ip_conflict and not serial_matches:
                raise ValidationError(
                    f"The IP conflict for {item.name or item.ip} lacks a matching charger identity."
                )
            return charger

        serial_number = cls.text(item.serial_number)
        if not serial_number:
            raise ValidationError(
                f"Charger {item.name or item.ip} needs an explicit inventory link or serial number."
            )
        matches = inventory.chargers_by_serial_identity.get(
            (item.manufacturer_id, serial_number),
            (),
        )
        if not matches:
            raise ValidationError(
                f"Charger {item.name or item.ip} needs a location before it can be imported."
            )
        if len(matches) > 1:
            raise ValidationError(
                f"Charger {item.name or item.ip} matches multiple inventory records."
            )
        return matches[0]

    @classmethod
    def _validate_matched_chassis(
        cls,
        *,
        item: DiscoveryQueue,
        chassis: WirelessChassis,
        api_device_id: str,
        serial_number: str,
    ) -> None:
        """Reject implicit manufacturer or identity changes for an existing chassis."""
        if chassis.manufacturer_id != item.manufacturer_id:
            raise ValidationError(
                f"The chassis linked to {item.name or item.ip} belongs to another manufacturer."
            )
        existing_api_device_id = cls.text(chassis.api_device_id)
        existing_serial_number = cls.text(chassis.serial_number)
        api_matches = bool(api_device_id and api_device_id == existing_api_device_id)
        serial_matches = bool(
            serial_number and existing_serial_number and serial_number == existing_serial_number
        )
        if serial_number and existing_serial_number and serial_number != existing_serial_number:
            raise ValidationError(
                f"The serial number for {item.name or item.ip} conflicts with existing inventory."
            )
        if item.existing_device_id is not None:
            if api_device_id != existing_api_device_id and not serial_matches:
                raise ValidationError(
                    f"The API identity for {item.name or item.ip} conflicts with existing inventory."
                )
            if item.is_ip_conflict and not (api_matches or serial_matches):
                raise ValidationError(
                    f"The IP conflict for {item.name or item.ip} lacks a matching chassis identity."
                )
            return
        if api_device_id and existing_api_device_id != api_device_id:
            raise ValidationError(
                f"The API identity for {item.name or item.ip} conflicts with existing inventory."
            )

    @staticmethod
    def _indexed_chassis_matches(
        *,
        item: DiscoveryQueue,
        inventory: LockedApprovalInventory,
        api_device_id: str,
        serial_number: str,
    ) -> tuple[WirelessChassis, ...]:
        """Union explicit and durable identity indexes without duplicate rows."""
        matches_by_pk: dict[int, WirelessChassis] = {}
        if item.existing_device_id is not None:
            explicit = inventory.chassis_by_pk.get(item.existing_device_id)
            if explicit is not None:
                matches_by_pk[int(explicit.pk)] = explicit
        if api_device_id:
            for candidate in inventory.chassis_by_api_identity.get(
                (item.manufacturer_id, api_device_id),
                (),
            ):
                matches_by_pk[int(candidate.pk)] = candidate
        if serial_number:
            for candidate in inventory.chassis_by_serial_identity.get(
                (item.manufacturer_id, serial_number),
                (),
            ):
                matches_by_pk[int(candidate.pk)] = candidate
        return tuple(matches_by_pk.values())

    @classmethod
    def resolve_chassis(
        cls,
        item: DiscoveryQueue,
        *,
        inventory: LockedApprovalInventory,
    ) -> ChassisApprovalTarget:
        """Resolve one chassis matching an explicit or durable pre-locked identity."""
        api_device_id = cls.text(item.api_device_id)
        serial_number = cls.text(item.serial_number)
        matches = cls._indexed_chassis_matches(
            item=item,
            inventory=inventory,
            api_device_id=api_device_id,
            serial_number=serial_number,
        )
        if len(matches) > 1:
            raise ValidationError(
                f"Discovery identities for {item.name or item.ip} match multiple chassis."
            )

        chassis = matches[0] if matches else None
        if chassis is not None:
            cls._validate_matched_chassis(
                item=item,
                chassis=chassis,
                api_device_id=api_device_id,
                serial_number=serial_number,
            )

        if not api_device_id and chassis is not None:
            api_device_id = cls.text(chassis.api_device_id)
        if not api_device_id and serial_number:
            api_device_id = cls.serial_api_id(serial_number)
        if not api_device_id:
            raise ValidationError(
                f"Device {item.name or item.ip} needs an API ID or serial number before import."
            )

        return ChassisApprovalTarget(chassis=chassis, api_device_id=api_device_id)

    @staticmethod
    def serial_api_id(serial_number: str) -> str:
        """Build a stable fallback that fits the chassis API identity column."""
        readable_identity = f"serial:{serial_number}"
        if len(readable_identity) <= 100:
            return readable_identity
        digest = sha256(serial_number.encode()).hexdigest()
        return f"serial-sha256:{digest}"

    @classmethod
    def chassis_values(
        cls,
        item: DiscoveryQueue,
        target: ChassisApprovalTarget,
    ) -> dict[str, Any]:
        """Build non-destructive normalized values for a managed chassis."""
        if target.chassis is not None and target.chassis.status == "retired":
            raise ValidationError(
                f"Retired chassis {target.chassis} cannot be imported from discovery."
            )

        status = (
            "provisioning"
            if target.chassis is not None and target.chassis.status == "discovered"
            else "online"
        )
        values: dict[str, Any] = {
            "manufacturer": item.manufacturer,
            "api_device_id": target.api_device_id,
            "ip": item.ip,
            "role": item.device_type.lower(),
            "is_online": True,
            "status": status,
        }
        optional_values = {
            "serial_number": cls.text(item.serial_number),
            "name": cls.text(item.name),
            "fqdn": cls.text(item.fqdn),
            "model": cls.text(item.model),
            "firmware_version": cls.text(item.firmware_version),
            "mac_address": cls.metadata_text(item, "mac_address", "macAddress"),
            "subnet_mask": cls.metadata_text(item, "subnet_mask", "subnetMask"),
            "gateway": cls.metadata_text(item, "gateway"),
        }
        values.update({key: value for key, value in optional_values.items() if value})
        return values

    @staticmethod
    def validate_role(item: DiscoveryQueue) -> None:
        """Reject entries that cannot be represented by managed inventory."""
        device_type = item.device_type.lower()
        if device_type == "charger":
            return
        valid_roles = {choice[0] for choice in WirelessChassis.DEVICE_ROLES}
        if device_type not in valid_roles:
            raise ValidationError(
                f"Unsupported wireless chassis role {item.device_type!r} for {item.name or item.ip}."
            )
