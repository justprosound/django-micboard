"""Batch conflict policy for discovery approval."""

from __future__ import annotations

from django.core.exceptions import ValidationError

from micboard.models.discovery.discovery_queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.services.sync.discovery_approval_inventory import ApprovalIPOwners
from micboard.services.sync.discovery_approval_resolution import (
    ChassisApprovalTarget,
    DiscoveryApprovalResolver,
)

type ApprovalTargetKey = tuple[str, int, str]
type ChassisIdentity = tuple[int, str]


class DiscoveryApprovalBatchPolicy:
    """Fail closed when selected entries disagree about inventory ownership."""

    def __init__(self, *, owners: ApprovalIPOwners) -> None:
        self.owners = owners
        self.ip_claims: dict[str, ApprovalTargetKey] = {}
        self.target_ips: dict[ApprovalTargetKey, str] = {}
        self.identity_serials: dict[ChassisIdentity, str] = {}
        self.identity_roles: dict[ChassisIdentity, str] = {}
        self.serial_identities: dict[tuple[int, str], ChassisIdentity] = {}
        self.existing_chassis_identities: dict[int, ChassisIdentity] = {}
        self.existing_charger_manufacturers: dict[int, int] = {}

    @staticmethod
    def _single_owner_id(
        *,
        owner_ids: tuple[int, ...],
        ip: str,
        owner_label: str,
    ) -> int | None:
        """Return one owner ID and reject legacy data with ambiguous owners."""
        if len(owner_ids) > 1:
            raise ValidationError(f"IP address {ip} ambiguously belongs to multiple {owner_label}.")
        return owner_ids[0] if owner_ids else None

    def _claim(self, *, item: DiscoveryQueue, target_key: ApprovalTargetKey) -> None:
        """Require a one-to-one mapping between requested IPs and targets."""
        ip = str(item.ip)
        prior_target = self.ip_claims.setdefault(ip, target_key)
        if prior_target != target_key:
            raise ValidationError(f"Selected entries assign {ip} to multiple devices.")
        prior_ip = self.target_ips.setdefault(target_key, ip)
        if prior_ip != ip:
            raise ValidationError(
                f"Selected entries assign multiple IP addresses to {item.name or target_key}."
            )

    def validate_charger(self, *, item: DiscoveryQueue, charger: Charger) -> None:
        """Validate existing and in-batch IP ownership for a charger target."""
        ip = str(item.ip)
        chassis_owner_id = self._single_owner_id(
            owner_ids=self.owners.chassis_ids.get(ip, ()),
            ip=ip,
            owner_label="wireless chassis",
        )
        if chassis_owner_id is not None:
            raise ValidationError(f"IP address {ip} already belongs to a wireless chassis.")

        charger_owner_id = self._single_owner_id(
            owner_ids=self.owners.charger_ids.get(ip, ()),
            ip=ip,
            owner_label="chargers",
        )
        if charger_owner_id is not None and charger_owner_id != charger.pk:
            raise ValidationError(f"IP address {ip} already belongs to another charger.")

        charger_id = int(charger.pk)
        previous_manufacturer_id = self.existing_charger_manufacturers.setdefault(
            charger_id,
            item.manufacturer_id,
        )
        if previous_manufacturer_id != item.manufacturer_id:
            raise ValidationError(
                f"Selected entries assign conflicting manufacturers to charger {charger_id}."
            )
        self._claim(item=item, target_key=("charger", charger_id, ""))

    def validate_chassis(
        self,
        *,
        item: DiscoveryQueue,
        target: ChassisApprovalTarget,
    ) -> None:
        """Validate durable identity, role, and IP ownership for one chassis entry."""
        ip = str(item.ip)
        charger_owner_id = self._single_owner_id(
            owner_ids=self.owners.charger_ids.get(ip, ()),
            ip=ip,
            owner_label="chargers",
        )
        if charger_owner_id is not None:
            raise ValidationError(f"IP address {ip} already belongs to a charger.")

        chassis_owner_id = self._single_owner_id(
            owner_ids=self.owners.chassis_ids.get(ip, ()),
            ip=ip,
            owner_label="wireless chassis",
        )
        if chassis_owner_id is not None and (
            target.chassis is None or chassis_owner_id != target.chassis.pk
        ):
            raise ValidationError(f"IP address {ip} already belongs to another chassis.")

        identity = (item.manufacturer_id, target.api_device_id)
        if target.chassis is None:
            target_key = ("chassis_identity", item.manufacturer_id, target.api_device_id)
        else:
            target_key = ("chassis", int(target.chassis.pk), "")
            previous_identity = self.existing_chassis_identities.setdefault(
                int(target.chassis.pk),
                identity,
            )
            if previous_identity != identity:
                raise ValidationError(
                    f"Selected entries assign conflicting API IDs to {target.chassis}."
                )
        self._claim(item=item, target_key=target_key)

        role = item.device_type.lower()
        previous_role = self.identity_roles.setdefault(identity, role)
        if previous_role != role:
            raise ValidationError(
                f"Selected entries assign conflicting roles to {item.name or identity}."
            )

        serial_number = DiscoveryApprovalResolver.text(item.serial_number)
        if not serial_number:
            return
        previous_serial = self.identity_serials.setdefault(identity, serial_number)
        if previous_serial != serial_number:
            raise ValidationError(
                f"Selected entries assign conflicting serial numbers to {item.name or identity}."
            )
        serial_key = (item.manufacturer_id, serial_number)
        previous_identity = self.serial_identities.setdefault(serial_key, identity)
        if previous_identity != identity:
            raise ValidationError(
                f"Selected entries assign conflicting API IDs to serial {serial_number}."
            )
