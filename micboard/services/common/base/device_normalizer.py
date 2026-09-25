"""Turn vendor device payloads into `NormalizedChassis`.

The shipped integrations report devices with the same field spellings and differ only in
their device families, so one normalizer serves both. Each integration supplies its
vocabulary: which raw type strings name which family, and what to call a family when the
payload carries no model name.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from micboard.models.device_specs import get_device_spec
from micboard.services.core.hardware import (
    UNKNOWN_BYTE_LEVEL,
    NormalizedChannel,
    NormalizedChassis,
    NormalizedUnit,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

UNKNOWN_FAMILY = "unknown"


def _first(payload: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first non-null value among a field's vendor spellings."""
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return default


def _text(value: Any) -> str:
    """Render an optional scalar as stripped text, treating null as empty."""
    return "" if value is None else str(value).strip()


def _format_runtime(minutes: Any) -> str:
    """Format a battery runtime in minutes as ``HH:MM``, or empty when unusable."""
    try:
        total = int(minutes)
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    return f"{total // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True)
class VendorDeviceNormalizer:
    """Normalize one integration's device and channel payloads.

    Attributes:
        manufacturer_code: Code the device specification catalogue files models under.
        family_aliases: Raw ``type`` values, upper-cased with ``-`` and spaces replaced by
            ``_``, mapped to a family key.
        family_labels: Family key mapped to the name used when a payload has neither a
            device name nor a model name.
    """

    manufacturer_code: str
    family_aliases: Mapping[str, str]
    family_labels: Mapping[str, str]

    def normalize_device(self, api_data: Mapping[str, Any]) -> NormalizedChassis | None:
        """Normalize one device payload, or return None when it is unusable.

        A payload is unusable when it has no identifier or its values cannot take the
        normalized shape. The payload is never logged, because it carries addresses and
        serial numbers.
        """
        try:
            api_device_id = _text(api_data.get("id"))
            if not api_device_id:
                logger.error("Device data missing 'id' field")
                return None

            channels = _first(api_data, "channels", default=[])
            if not isinstance(channels, list):
                raise TypeError("Device channels must be a list")

            model = _text(_first(api_data, "model_name", "modelName"))
            return NormalizedChassis(
                api_device_id=api_device_id,
                ip=_text(_first(api_data, "ip", "ip_address", "ipAddress")),
                serial_number=_text(_first(api_data, "serial_number", "serialNumber")),
                mac_address=_first(api_data, "mac_address", "macAddress", default=""),
                name=(
                    _text(_first(api_data, "name", "device_name", "deviceName"))
                    or model
                    or self._family_label(api_data)
                ),
                model=model,
                role=self._role(model),
                firmware_version=_text(_first(api_data, "firmware_version", "firmwareVersion")),
                channels=self.normalize_channels(channels),
            )
        except Exception as exc:
            logger.exception(
                "Error normalizing %s device data; payload redacted",
                self.manufacturer_code,
                exc_info=sanitized_exception_info(exc),
            )
            return None

    def normalize_channels(
        self,
        api_channels: Iterable[Mapping[str, Any]],
    ) -> list[NormalizedChannel]:
        """Normalize the channel list a device embeds or a channel endpoint returns.

        Every channel is kept. A channel whose linked unit is absent or unusable carries
        ``unit=None``.

        Raises:
            TypeError, ValueError: A channel entry is not a mapping or has no usable number.
        """
        normalized: list[NormalizedChannel] = []
        for channel_data in api_channels:
            number = int(_first(channel_data, "channel", "channelNumber", default=0))
            unit_data = _first(channel_data, "tx", "transmitter")
            unit = (
                self._normalize_unit(unit_data, number)
                if isinstance(unit_data, Mapping) and unit_data
                else None
            )
            normalized.append(NormalizedChannel(number=number, unit=unit))
        return normalized

    def _normalize_unit(
        self,
        unit_data: Mapping[str, Any],
        channel_number: int,
    ) -> NormalizedUnit | None:
        """Normalize one linked unit, or return None when its values are unusable."""
        try:
            return NormalizedUnit(
                slot=_first(unit_data, "slot", default=channel_number),
                battery=_first(
                    unit_data, "battery_bars", "batteryBars", default=UNKNOWN_BYTE_LEVEL
                ),
                battery_charge=_first(unit_data, "battery_charge", "batteryCharge"),
                battery_type=_text(_first(unit_data, "battery_type", "batteryType")),
                runtime=_format_runtime(
                    _first(unit_data, "battery_runtime_minutes", "batteryRuntimeMinutes")
                ),
                battery_health=_text(_first(unit_data, "battery_health", "batteryHealth")),
                battery_cycles=_first(unit_data, "battery_cycles", "batteryCycles"),
                battery_temperature_c=_first(
                    unit_data, "battery_temperature_c", "batteryTemperatureC"
                ),
                audio_level=_first(unit_data, "audio_level", "audioLevel", default=0),
                rf_level=_first(unit_data, "rf_level", "rfLevel", default=0),
                frequency=_text(unit_data.get("frequency")),
                antenna=_text(unit_data.get("antenna")),
                tx_offset=_first(unit_data, "tx_offset", "txOffset", default=UNKNOWN_BYTE_LEVEL),
                quality=_first(
                    unit_data, "audio_quality", "audioQuality", default=UNKNOWN_BYTE_LEVEL
                ),
                status=_text(unit_data.get("status")),
                name=_text(_first(unit_data, "name", "deviceName")),
            )
        except Exception as exc:
            logger.exception(
                "Error normalizing %s unit data; payload redacted",
                self.manufacturer_code,
                exc_info=sanitized_exception_info(exc),
            )
            return None

    def _family_label(self, api_data: Mapping[str, Any]) -> str:
        """Return a readable label for the device family the payload's type names."""
        raw_type = _text(api_data.get("type")).upper().replace("-", "_").replace(" ", "_")
        family = self.family_aliases.get(raw_type, UNKNOWN_FAMILY)
        return self.family_labels.get(family, "Unknown")

    def _role(self, model: str) -> str | None:
        """Return the chassis role the device specification records for a model."""
        spec = get_device_spec(manufacturer=self.manufacturer_code, model=model)
        role = spec.get("role") if spec else None
        return role if isinstance(role, str) else None
