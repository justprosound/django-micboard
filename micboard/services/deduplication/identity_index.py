"""Bulk identity index for bounded manufacturer synchronization."""

from __future__ import annotations

from collections.abc import Hashable, Iterator
from dataclasses import dataclass, field
from itertools import islice
from typing import TYPE_CHECKING, TypeVar

from django.db import connection
from django.db.models import QuerySet
from django.utils.ipv6 import clean_ipv6_address

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.utils.mac_address import canonicalize_mac_address, mac_address_query_variants

if TYPE_CHECKING:
    from collections.abc import Iterable

    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.services.core.hardware import NormalizedHardware

IdentityKey = TypeVar("IdentityKey", bound=Hashable)
MAX_IDENTITY_QUERY_VALUES = 500


@dataclass(slots=True)
class DeviceIdentityIndex:
    """In-memory identity lookups populated with bounded bulk queries."""

    by_serial: dict[str, list[WirelessChassis]] = field(default_factory=dict)
    by_mac: dict[str, list[WirelessChassis]] = field(default_factory=dict)
    by_ip: dict[str, list[WirelessChassis]] = field(default_factory=dict)
    by_api_id: dict[tuple[int, str], list[WirelessChassis]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        payloads: Iterable[NormalizedHardware],
        *,
        manufacturer: Manufacturer,
    ) -> DeviceIdentityIndex:
        """Fetch relevant identities in backend-safe chunks, never per device."""
        payload_list = list(payloads)
        serials = {payload.serial_number for payload in payload_list if payload.serial_number}
        macs = {
            normalized_mac
            for payload in payload_list
            if (normalized_mac := canonicalize_mac_address(payload.mac_address))
        }
        ips = {cls._ip_key(payload.ip) for payload in payload_list}
        api_ids = {payload.api_device_id for payload in payload_list}

        chassis_by_pk: dict[int, WirelessChassis] = {}
        querysets = cls._identity_querysets(
            serials=serials,
            macs=macs,
            ips=ips,
            api_ids=api_ids,
            manufacturer=manufacturer,
        )
        for queryset in querysets:
            for chassis in queryset.select_related("manufacturer").order_by():
                chassis_by_pk.setdefault(chassis.pk, chassis)

        index = cls()
        for chassis in chassis_by_pk.values():
            if chassis.serial_number in serials:
                index._append(index.by_serial, chassis.serial_number, chassis)
            chassis_mac = canonicalize_mac_address(chassis.mac_address)
            if chassis_mac and chassis_mac in macs:
                index._append(index.by_mac, chassis_mac, chassis)
            chassis_ip = cls._ip_key(chassis.ip)
            if chassis_ip in ips:
                index._append(index.by_ip, chassis_ip, chassis)
            api_key = (chassis.manufacturer_id, chassis.api_device_id)
            if chassis.manufacturer_id == manufacturer.pk and chassis.api_device_id in api_ids:
                index._append(index.by_api_id, api_key, chassis)
        return index

    def serial(self, value: str) -> WirelessChassis | None:
        """Resolve one serial using the same ambiguity behavior as ``QuerySet.get``."""
        return self._unique(self.by_serial, value, "serial_number")

    def mac(self, value: str) -> WirelessChassis | None:
        """Resolve one MAC address using the same ambiguity behavior as ``QuerySet.get``."""
        canonical = canonicalize_mac_address(value)
        if canonical is None:
            return None
        return self._unique(self.by_mac, canonical, "mac_address")

    def ip(self, value: str) -> WirelessChassis | None:
        """Resolve one IP address using the same ambiguity behavior as ``QuerySet.get``."""
        return self._unique(self.by_ip, self._ip_key(value), "ip")

    def api_id(self, manufacturer_id: int, value: str) -> WirelessChassis | None:
        """Resolve a manufacturer-scoped API device identifier."""
        return self._unique(self.by_api_id, (manufacturer_id, value), "api_device_id")

    def add(self, chassis: WirelessChassis) -> None:
        """Add a chassis created during this batch so later payloads see it."""
        if chassis.serial_number:
            self._append(self.by_serial, chassis.serial_number, chassis)
        if canonical_mac := canonicalize_mac_address(chassis.mac_address):
            self._append(self.by_mac, canonical_mac, chassis)
        self._append(self.by_ip, self._ip_key(chassis.ip), chassis)
        self._append(
            self.by_api_id,
            (chassis.manufacturer_id, chassis.api_device_id),
            chassis,
        )

    def move_ip(self, chassis: WirelessChassis, *, old_ip: str) -> None:
        """Refresh the IP index after a moved chassis is persisted."""
        old_key = self._ip_key(old_ip)
        old_matches = self.by_ip.get(old_key, [])
        self.by_ip[old_key] = [candidate for candidate in old_matches if candidate.pk != chassis.pk]
        if not self.by_ip[old_key]:
            self.by_ip.pop(old_key, None)
        self._append(self.by_ip, self._ip_key(chassis.ip), chassis)

    @classmethod
    def _identity_querysets(
        cls,
        *,
        serials: set[str],
        macs: set[str],
        ips: set[str],
        api_ids: set[str],
        manufacturer: Manufacturer,
    ) -> Iterator[QuerySet[WirelessChassis]]:
        yield from cls._chunked_querysets("serial_number", serials)
        mac_variants = {variant for mac in macs for variant in mac_address_query_variants(mac)}
        yield from cls._chunked_querysets("mac_address", mac_variants)
        yield from cls._chunked_querysets("ip", ips)
        yield from cls._chunked_querysets(
            "api_device_id",
            api_ids,
            manufacturer=manufacturer,
        )

    @staticmethod
    def _chunked_querysets(
        field_name: str,
        values: set[str],
        *,
        manufacturer: Manufacturer | None = None,
    ) -> Iterator[QuerySet[WirelessChassis]]:
        """Stay below backend parameter limits while retaining bounded bulk reads."""
        max_parameters = connection.features.max_query_params
        reserved_parameters = 1 if manufacturer is not None else 0
        backend_limit = (
            max(max_parameters - reserved_parameters, 1)
            if max_parameters is not None
            else MAX_IDENTITY_QUERY_VALUES
        )
        chunk_size = min(MAX_IDENTITY_QUERY_VALUES, backend_limit)
        values_iterator = iter(values)
        while chunk := tuple(islice(values_iterator, chunk_size)):
            filters: dict[str, object] = {f"{field_name}__in": chunk}
            if manufacturer is not None:
                filters["manufacturer"] = manufacturer
            yield WirelessChassis.objects.filter(**filters)

    @staticmethod
    def _ip_key(value: str) -> str:
        """Match GenericIPAddressField's canonical IPv6 representation."""
        return clean_ipv6_address(value) if ":" in value else value

    @staticmethod
    def _append(
        mapping: dict[IdentityKey, list[WirelessChassis]],
        key: IdentityKey,
        chassis: WirelessChassis,
    ) -> None:
        matches = mapping.setdefault(key, [])
        if all(candidate.pk != chassis.pk for candidate in matches):
            matches.append(chassis)

    @staticmethod
    def _unique(
        mapping: dict[IdentityKey, list[WirelessChassis]],
        key: IdentityKey,
        field_name: str,
    ) -> WirelessChassis | None:
        matches = mapping.get(key, [])
        if len(matches) > 1:
            raise WirelessChassis.MultipleObjectsReturned(
                f"get() returned more than one WirelessChassis for {field_name}"
            )
        return matches[0] if matches else None
