"""Manufacturer-neutral normalization for hardware payloads."""

from __future__ import annotations

from typing import Any

from pydantic import field_validator

from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.utils.mac_address import canonicalize_mac_address


class NormalizedHardware(PydanticBaseDTO):
    """Normalized hardware payload independent of manufacturer key names."""

    api_device_id: str
    ip: str
    serial_number: str
    mac_address: str
    name: str
    model: str
    device_type: str
    firmware_version: str
    hosted_firmware_version: str
    description: str
    subnet_mask: str | None
    gateway: str | None
    network_mode: str
    interface_id: str

    @field_validator("mac_address", mode="before")
    @classmethod
    def canonicalize_mac(cls, value: Any) -> str:
        """Canonicalize hardware identity on creation and assignment."""
        return canonicalize_mac_address(value) or ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> NormalizedHardware | None:
        """Best-effort normalization for heterogeneous vendor payloads."""
        api_device_id = (data.get("id") or data.get("api_device_id") or "").strip()
        ip = (
            data.get("ip")
            or data.get("ipAddress")
            or data.get("ipv4")
            or data.get("ip_address")
            or ""
        ).strip()

        if not api_device_id or not ip:
            return None

        serial_number = (
            data.get("serial_number") or data.get("serialNumber") or data.get("serial") or ""
        ).strip()
        mac_address = (
            canonicalize_mac_address(
                (data.get("mac_address") or data.get("macAddress") or data.get("mac") or "").strip()
            )
            or ""
        )

        return cls(
            api_device_id=api_device_id,
            ip=ip,
            serial_number=serial_number,
            mac_address=mac_address,
            name=(data.get("name") or data.get("model") or "").strip(),
            model=(data.get("model") or "").strip(),
            device_type=(data.get("device_type") or "").strip(),
            firmware_version=(
                data.get("firmware")
                or data.get("firmware_version")
                or data.get("firmwareVersion")
                or ""
            ).strip(),
            hosted_firmware_version=(data.get("hosted_firmware_version") or "").strip(),
            description=(data.get("description") or "").strip(),
            subnet_mask=data.get("subnet_mask") or data.get("subnetMask"),
            gateway=data.get("gateway"),
            network_mode=(data.get("network_mode") or data.get("networkMode") or "auto").strip(),
            interface_id=(data.get("interface_id") or data.get("interfaceId") or "").strip(),
        )
