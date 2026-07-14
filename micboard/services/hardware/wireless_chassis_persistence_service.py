"""Authoritative WirelessChassis create and metadata-update boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

from django.apps import apps
from django.db import router, transaction
from django.utils import timezone

from micboard.exceptions import OrganizationDeviceQuotaExceededError
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.utils.mac_address import canonicalize_mac_address

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.multitenancy.models import Organization
    from micboard.services.core.hardware import NormalizedHardware


class WirelessChassisPersistenceService:
    """Persist chassis fields while keeping source-specific orchestration outside.

    Organization ownership is derived exclusively from ``location.building``.
    Locationless chassis are platform inventory and do not consume an organization
    quota until the domain has an explicit non-location ownership contract.
    """

    @staticmethod
    def _values(write: WirelessChassisWrite) -> dict[str, Any]:
        """Return only fields explicitly supplied by the caller."""
        return write.model_dump(exclude_unset=True)

    @staticmethod
    def _organization_id_for_values(
        values: dict[str, Any],
        *,
        using: str,
    ) -> int | None:
        """Resolve persisted location ownership without trusting caller-side relations."""
        if not apps.is_installed("micboard.multitenancy"):
            return None
        location_id = getattr(values.get("location"), "pk", None)
        if location_id is None:
            return None

        from micboard.models.locations.structure import Location

        organization_id = (
            Location._base_manager.using(using)
            .filter(pk=location_id)
            .values_list("building__organization_id", flat=True)
            .first()
        )
        return int(organization_id) if organization_id is not None else None

    @classmethod
    @contextmanager
    def _locked_organization(
        cls,
        values: dict[str, Any],
        *,
        using: str,
    ) -> Iterator[Organization | None]:
        """Lock the owning organization for the complete quota-check/create window."""
        organization_id = cls._organization_id_for_values(values, using=using)
        if organization_id is None:
            yield None
            return

        organization_model = apps.get_model("micboard_multitenancy", "Organization")
        with transaction.atomic(using=using):
            organization = cast(
                "Organization | None",
                (
                    organization_model._default_manager.using(using)
                    .select_for_update()
                    .filter(pk=organization_id)
                    .only("pk", "max_devices")
                    .first()
                ),
            )
            yield organization

    @staticmethod
    def _enforce_create_quota(
        organization: Organization | None,
        *,
        using: str,
    ) -> None:
        """Reject only a new organization-owned chassis above a finite quota."""
        if organization is None or organization.max_devices is None:
            return

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        current_devices = (
            WirelessChassis._base_manager.using(using)
            .filter(
                location__building__organization_id=organization.pk,
            )
            .count()
        )
        if current_devices + 1 <= organization.max_devices:
            return
        raise OrganizationDeviceQuotaExceededError(
            organization_id=organization.pk,
            max_devices=organization.max_devices,
            current_devices=current_devices,
        )

    @staticmethod
    def _persisted_organization_id(
        *,
        chassis_id: int | None,
        using: str,
    ) -> int | None:
        """Read current ownership from the database for quota-transfer decisions."""
        if chassis_id is None or not apps.is_installed("micboard.multitenancy"):
            return None

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        organization_id = (
            WirelessChassis._base_manager.using(using)
            .filter(pk=chassis_id)
            .values_list("location__building__organization_id", flat=True)
            .first()
        )
        return int(organization_id) if organization_id is not None else None

    @classmethod
    def create(
        cls,
        *,
        manufacturer: Manufacturer | None = None,
        write: WirelessChassisWrite,
        using: str | None = None,
    ) -> WirelessChassis:
        """Create one chassis after validating its required external identity."""
        values = cls._values(write)
        write_manufacturer = values.pop("manufacturer", None)
        selected_manufacturer = manufacturer or write_manufacturer
        if selected_manufacturer is None:
            raise ValueError("Wireless chassis creation requires a manufacturer")
        if not values.get("api_device_id") or not values.get("ip"):
            raise ValueError("Wireless chassis creation requires api_device_id and ip")

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        database = using or router.db_for_write(WirelessChassis)
        manager = WirelessChassis.objects.db_manager(database)
        with cls._locked_organization(values, using=database) as organization:
            cls._enforce_create_quota(organization, using=database)
            return manager.create(manufacturer=selected_manufacturer, **values)

    @classmethod
    def update(
        cls,
        *,
        chassis: WirelessChassis,
        write: WirelessChassisWrite,
        using: str | None = None,
        save_all_fields: bool = False,
    ) -> WirelessChassis:
        """Apply and persist exactly the explicitly supplied chassis fields."""
        values = cls._values(write)
        if not values:
            return chassis

        def persist(*, database: str | None) -> None:
            for field, value in values.items():
                setattr(chassis, field, value)
            save_kwargs: dict[str, Any] = {}
            if not save_all_fields:
                save_kwargs["update_fields"] = list(values)
            if database is not None:
                save_kwargs["using"] = database
            chassis.save(**save_kwargs)

        if "location" not in values:
            persist(database=using)
            return chassis

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        database = using or router.db_for_write(WirelessChassis, instance=chassis)
        with cls._locked_organization(values, using=database) as organization:
            current_organization_id = cls._persisted_organization_id(
                chassis_id=getattr(chassis, "pk", None),
                using=database,
            )
            if organization is not None and current_organization_id != organization.pk:
                cls._enforce_create_quota(organization, using=database)
            persist(database=database)
        return chassis

    @classmethod
    def upsert(
        cls,
        *,
        manufacturer: Manufacturer,
        api_device_id: str,
        defaults: WirelessChassisWrite,
        create_defaults: WirelessChassisWrite | None = None,
        using: str | None = None,
    ) -> tuple[WirelessChassis, bool]:
        """Update or create one chassis using its manufacturer-scoped API identity."""
        if not api_device_id:
            raise ValueError("Wireless chassis upsert requires api_device_id")
        update_values = cls._values(defaults)
        created_values = cls._values(create_defaults or defaults)
        update_values.pop("manufacturer", None)
        created_values.pop("manufacturer", None)
        update_values.pop("api_device_id", None)
        created_values.pop("api_device_id", None)

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        database = using or router.db_for_write(WirelessChassis)
        manager = WirelessChassis.objects.db_manager(database)
        lookup = {
            "api_device_id": api_device_id,
            "manufacturer": manufacturer,
        }
        with cls._locked_organization(created_values, using=database) as organization:
            current_organization_id = (
                manager.filter(**lookup)
                .values_list("location__building__organization_id", flat=True)
                .first()
            )
            if organization is not None and current_organization_id != organization.pk:
                cls._enforce_create_quota(organization, using=database)
            return manager.update_or_create(
                **lookup,
                defaults=update_values,
                create_defaults=created_values,
            )

    @classmethod
    def create_from_normalized(
        cls,
        *,
        manufacturer: Manufacturer,
        payload: NormalizedHardware,
        initial_status: str | None = None,
    ) -> WirelessChassis:
        """Create a complete chassis from manufacturer-normalized inventory."""
        write = WirelessChassisWrite(
            api_device_id=payload.api_device_id,
            serial_number=payload.serial_number,
            mac_address=canonicalize_mac_address(payload.mac_address),
            ip=payload.ip,
            name=payload.name,
            model=payload.model,
            role=cls.role_for_device_type(payload.device_type),
            firmware_version=payload.firmware_version,
            hosted_firmware_version=payload.hosted_firmware_version,
            description=payload.description,
            subnet_mask=payload.subnet_mask,
            gateway=payload.gateway,
            network_mode=payload.network_mode,
            interface_id=payload.interface_id,
            last_seen=timezone.now(),
        )
        if initial_status is not None:
            write = write.model_copy(update={"status": initial_status})
        return cls.create(
            manufacturer=manufacturer,
            write=write,
        )

    @classmethod
    def update_from_normalized(
        cls,
        *,
        chassis: WirelessChassis,
        payload: NormalizedHardware,
        set_ip: bool = False,
    ) -> WirelessChassis:
        """Refresh normalized metadata without erasing useful values with blanks."""
        values: dict[str, Any] = {}
        if set_ip:
            values["ip"] = payload.ip
        values.update(
            name=payload.name or chassis.name,
            model=payload.model or chassis.model,
            role=(
                cls.role_for_device_type(payload.device_type)
                if payload.device_type
                else chassis.role
            ),
            firmware_version=payload.firmware_version or chassis.firmware_version,
            hosted_firmware_version=(
                payload.hosted_firmware_version or chassis.hosted_firmware_version
            ),
            description=payload.description or chassis.description,
            subnet_mask=payload.subnet_mask or chassis.subnet_mask,
            gateway=payload.gateway or chassis.gateway,
            network_mode=payload.network_mode or chassis.network_mode,
            interface_id=payload.interface_id or chassis.interface_id,
            last_seen=timezone.now(),
        )
        incoming_mac = canonicalize_mac_address(payload.mac_address)
        existing_mac = canonicalize_mac_address(getattr(chassis, "mac_address", None))
        if incoming_mac and incoming_mac == existing_mac and chassis.mac_address != incoming_mac:
            values["mac_address"] = incoming_mac
        return cls.update(chassis=chassis, write=WirelessChassisWrite(**values))

    @staticmethod
    def role_for_device_type(device_type: object) -> str:
        """Map manufacturer type text to a supported chassis role."""
        normalized = device_type.lower() if isinstance(device_type, str) else ""
        if "transmitter" in normalized:
            return "transmitter"
        if "transceiver" in normalized:
            return "transceiver"
        return "receiver"
