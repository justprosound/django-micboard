"""Policy for scheduling discovery after chassis identity persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from micboard.services.shared.base_dto import PydanticBaseDTO

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis


class ChassisDiscoveryIdentity(PydanticBaseDTO):
    """Persisted chassis fields used by discovery deduplication."""

    manufacturer_id: int
    api_device_id: str
    serial_number: str
    mac_address: str | None
    ip: str

    @classmethod
    def from_chassis(cls, chassis: WirelessChassis) -> ChassisDiscoveryIdentity:
        """Map a chassis instance to its discovery identity."""
        return cls(
            manufacturer_id=chassis.manufacturer_id,
            api_device_id=chassis.api_device_id,
            serial_number=chassis.serial_number,
            mac_address=chassis.mac_address,
            ip=str(chassis.ip),
        )


class ChassisDiscoveryScheduleService:
    """Identify manufacturers affected by a durable chassis identity write."""

    _UPDATE_FIELDS: ClassVar[dict[str, frozenset[str]]] = {
        "manufacturer_id": frozenset({"manufacturer", "manufacturer_id"}),
        "api_device_id": frozenset({"api_device_id"}),
        "serial_number": frozenset({"serial_number"}),
        "mac_address": frozenset({"mac_address"}),
        "ip": frozenset({"ip"}),
    }

    @classmethod
    def affected_manufacturer_ids(
        cls,
        chassis: WirelessChassis,
        *,
        created: bool,
        using: str,
        update_fields: frozenset[str] | None,
    ) -> tuple[int, ...]:
        """Return owners needing reconciliation after this persisted write."""
        if created:
            return (chassis.manufacturer_id,)

        compared_fields = tuple(cls._UPDATE_FIELDS)
        if update_fields is not None:
            compared_fields = tuple(
                field
                for field, aliases in cls._UPDATE_FIELDS.items()
                if not aliases.isdisjoint(update_fields)
            )
        if not compared_fields:
            return ()

        previous_values = (
            type(chassis)._base_manager.using(using).values(*cls._UPDATE_FIELDS).get(pk=chassis.pk)
        )
        previous_values["ip"] = str(previous_values["ip"])
        previous = ChassisDiscoveryIdentity.model_validate(previous_values)
        current = ChassisDiscoveryIdentity.from_chassis(chassis)
        if not any(
            getattr(previous, field) != getattr(current, field) for field in compared_fields
        ):
            return ()

        return tuple(sorted({previous.manufacturer_id, current.manufacturer_id}))
