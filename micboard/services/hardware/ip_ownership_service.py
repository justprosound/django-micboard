"""Cross-model IP ownership for managed network hardware."""

from __future__ import annotations

import hashlib
import ipaddress
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import connections

if TYPE_CHECKING:
    from django.db.models import Model


class HardwareIPOwnershipService:
    """Serialize and validate IP ownership across hardware model tables."""

    @staticmethod
    def _canonical_ip(value: Any) -> str | None:
        """Return a canonical address, preserving nullable charger addresses."""
        if value in (None, ""):
            return None
        return str(ipaddress.ip_address(str(value)))

    @staticmethod
    def _advisory_lock_key(ip: str) -> int:
        """Derive a stable signed PostgreSQL advisory-lock key."""
        digest = hashlib.sha256(f"micboard:hardware-ip:{ip}".encode()).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    @classmethod
    def _lock_address(cls, *, ip: str, using: str) -> None:
        """Serialize an address claim for the current database transaction."""
        connection = connections[using]
        if not connection.in_atomic_block:
            raise RuntimeError("Hardware IP ownership checks require an atomic transaction.")
        if connection.vendor != "postgresql":
            return

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                [cls._advisory_lock_key(ip)],
            )

    @classmethod
    def lock_addresses(cls, values: Iterable[Any], *, using: str) -> None:
        """Lock unique canonical addresses in one deterministic order."""
        addresses = sorted(
            {address for value in values if (address := cls._canonical_ip(value)) is not None}
        )
        for address in addresses:
            cls._lock_address(ip=address, using=using)

    @classmethod
    def validate_for_instance(cls, *, instance: Model, using: str) -> None:
        """Lock and reject an address already owned by another hardware kind."""
        ip = cls._canonical_ip(getattr(instance, "ip", None))
        if ip is None:
            return

        cls._lock_address(ip=ip, using=using)

        from micboard.models.hardware.charger import Charger
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        conflicting_model: type[Model]
        if isinstance(instance, WirelessChassis):
            conflicting_model = Charger
            conflict_label = "charger"
        elif isinstance(instance, Charger):
            conflicting_model = WirelessChassis
            conflict_label = "wireless chassis"
        else:  # pragma: no cover - service contract guard
            raise TypeError(f"Unsupported hardware model: {type(instance).__name__}")

        if conflicting_model._default_manager.using(using).filter(ip=ip).exists():
            raise ValidationError(
                {"ip": f"This address is already assigned to a {conflict_label}."}
            )
