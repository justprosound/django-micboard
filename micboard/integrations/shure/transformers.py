"""Data transformers for converting Shure System API format to micboard format.

This module handles all data transformation logic, including:
- Device data transformation
- Transmitter data transformation
- Device model identification
- Type mapping and formatting utilities
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ShureDataTransformer:
    """Handles transformation of Shure API data to micboard format."""

    @staticmethod
    def transform_device_data(api_data: dict) -> dict | None:
        """Transform Shure API format to micboard format with comprehensive error handling.

        Args:
            api_data: Raw device data from Shure System API

        Returns:
            Transformed device data dict, or None if transformation fails
        """
        try:
            device_id = api_data.get("id")
            if not device_id:
                logger.error("Device data missing 'id' field")
                return None

            identity = ShureDataTransformer.identify_device_model(api_data)
            device_type = identity["type"]
            logger.debug(
                "Transforming device %s (type: %s, model: %s)",
                device_id,
                device_type,
                identity.get("model"),
            )

            result = {
                "id": device_id,
                "ip": api_data.get("ip_address", api_data.get("ipAddress", "")),
                "type": device_type,
                "name": identity.get("model", ""),
                "firmware": identity.get("firmware", ""),
                # Additional device details (populated if present or via enrichment)
                "serial": api_data.get("serial_number", api_data.get("serialNumber")),
                "hostname": api_data.get("hostname"),
                "mac_address": api_data.get("mac_address", api_data.get("macAddress")),
                "model_variant": api_data.get("model_variant", api_data.get("modelVariant")),
                "band": api_data.get("frequency_band", api_data.get("frequencyBand")),
                "location": api_data.get("location"),
                # Best-effort extra info bucket for consumers that want more detail
                "info": {
                    "raw_type": identity.get("raw_type", ""),
                    "raw_model": identity.get("raw_model", ""),
                    "uptime_minutes": api_data.get("uptime_minutes", api_data.get("uptimeMinutes")),
                    "temperature_c": api_data.get("temperature_c", api_data.get("temperatureC")),
                },
                "channels": [],
            }

            # Transform channel data
            channels_data = api_data.get("channels", [])
            logger.debug("Processing %d channels for device %s", len(channels_data), device_id)

            for channel_data in channels_data:
                channel_num = channel_data.get("channel", channel_data.get("channelNumber", 0))
                tx_data = channel_data.get("tx", channel_data.get("transmitter", {}))

                # Only add channel if transmitter data exists
                if tx_data and isinstance(tx_data, dict):
                    transformed_tx = ShureDataTransformer.transform_transmitter_data(
                        tx_data, channel_num
                    )
                    if transformed_tx:
                        result["channels"].append(
                            {
                                "channel": channel_num,
                                "tx": transformed_tx,
                            }
                        )
                else:
                    logger.debug(
                        "No transmitter data for device %s channel %d",
                        device_id,
                        channel_num,
                    )

            logger.debug(
                "Successfully transformed device %s with %d channels",
                device_id,
                len(result["channels"]),
            )
            return result
        except Exception:
            logger.exception("Error transforming device data for device %s", api_data.get("id"))
            return None

    @staticmethod
    def identify_device_model(api_data: dict) -> dict:
        """Identify and normalize device model information from Shure System API payload.

        Args:
            api_data: Raw device data from Shure System API

        Returns:
            dict with keys:
                - model: Human-readable model name (e.g., 'ULX-D', 'QLX-D')
                - type: Normalized family key used by micboard (e.g., 'ulxd', 'qlxd')
                - firmware: Firmware version string (if available)
                - raw_type: Raw API 'type' value (if available)
                - raw_model: Raw API model field value (if available)
        """
        raw_type = api_data.get("type")
        raw_model = api_data.get("model_name", api_data.get("modelName"))
        firmware = api_data.get("firmware_version", api_data.get("firmwareVersion")) or ""

        norm_type = ShureDataTransformer._map_device_type(raw_type or "unknown")

        # Derive a friendly model label if Shure provides nothing
        if not raw_model:
            fallback_model = {
                "ulxd": "ULX-D",
                "qlxd": "QLX-D",
                "uhfr": "UHF-R",
                "axtd": "Axient Digital",
                "p10t": "P10T",
            }.get(norm_type, "Unknown")
            model = fallback_model
        else:
            model = str(raw_model)

        return {
            "model": model,
            "type": norm_type,
            "firmware": str(firmware),
            "raw_type": raw_type or "",
            "raw_model": raw_model or "",
        }

    @staticmethod
    def transform_transmitter_data(tx_data: dict, channel_num: int) -> dict | None:
        """Transform transmitter data from Shure API format to micboard format.

        Handles various field name variations and provides sensible defaults.

        Args:
            tx_data: Raw transmitter data from Shure System API
            channel_num: Channel number for this transmitter

        Returns:
            Transformed transmitter data dict, or None if transformation fails
        """
        try:
            # Battery data - handle both 'bars' and 'charge' formats
            battery_bars = tx_data.get("battery_bars", tx_data.get("batteryBars", 255))
            battery_charge = tx_data.get("battery_charge", tx_data.get("batteryCharge"))
            battery_runtime = tx_data.get(
                "battery_runtime_minutes", tx_data.get("batteryRuntimeMinutes")
            )

            # Audio and RF levels
            audio_level = tx_data.get("audio_level", tx_data.get("audioLevel", 0))
            rf_level = tx_data.get("rf_level", tx_data.get("rfLevel", 0))

            # Frequency and antenna
            frequency = tx_data.get("frequency", "")
            antenna = tx_data.get("antenna", "")

            # Status and quality
            status = tx_data.get("status", "")
            quality = tx_data.get("audio_quality", tx_data.get("audioQuality", 255))
            tx_offset = tx_data.get("tx_offset", tx_data.get("txOffset", 255))

            # Transmitter name
            name = tx_data.get("name", tx_data.get("deviceName", ""))

            # Slot assignment - use channel number if not explicitly provided
            slot = tx_data.get("slot", channel_num)

            # Optional extra details not required by core micboard views
            extra = {
                "encryption": tx_data.get("encryption"),
                "rf_quality": tx_data.get("rf_quality", tx_data.get("rfQuality")),
                "diversity": tx_data.get("diversity"),
                "antenna_metrics": {
                    "a": tx_data.get("rfAntennaA", tx_data.get("rf_antenna_a")),
                    "b": tx_data.get("rfAntennaB", tx_data.get("rf_antenna_b")),
                },
                "clip": tx_data.get("clip"),
                "peak": tx_data.get("peak"),
                "battery_health": tx_data.get("battery_health", tx_data.get("batteryHealth")),
                "battery_cycles": tx_data.get("battery_cycles", tx_data.get("batteryCycles")),
                "battery_temperature_c": tx_data.get(
                    "battery_temperature_c", tx_data.get("batteryTemperatureC")
                ),
            }

            return {
                "battery": battery_bars,
                "battery_charge": battery_charge,
                "audio_level": audio_level,
                "rf_level": rf_level,
                "frequency": str(frequency) if frequency else "",
                "antenna": str(antenna) if antenna else "",
                "tx_offset": tx_offset,
                "quality": quality,
                "runtime": ShureDataTransformer._format_runtime(battery_runtime),
                "status": str(status) if status else "",
                # Additional transmitter details when available
                "mute": tx_data.get("mute", tx_data.get("isMuted")),
                "power": tx_data.get("power", tx_data.get("txPower")),
                "battery_type": tx_data.get("battery_type", tx_data.get("batteryType")),
                "temperature": tx_data.get("temperature"),
                "rf_antenna_a": tx_data.get("rfAntennaA", tx_data.get("rf_antenna_a")),
                "rf_antenna_b": tx_data.get("rfAntennaB", tx_data.get("rf_antenna_b")),
                "name": str(name) if name else "",
                "name_raw": str(name) if name else "",
                "slot": slot,
                "extra": extra,
            }
        except Exception:
            logger.exception("Error transforming transmitter data for channel %d", channel_num)
            return None

    @staticmethod
    def _map_device_type(api_type: str) -> str:
        """Map Shure API device types to micboard types.

        Handles various naming conventions from the Shure System API.

        Args:
            api_type: Device type string from Shure API

        Returns:
            Normalized device type for micboard
        """
        if not api_type:
            return "unknown"

        api_type_upper = api_type.upper().replace("-", "_").replace(" ", "_")

        type_map = {
            "UHFR": "uhfr",
            "UHF_R": "uhfr",
            "QLXD": "qlxd",
            "QLX_D": "qlxd",
            "ULXD": "ulxd",
            "ULX_D": "ulxd",
            "AXIENT_DIGITAL": "axtd",
            "AXIENTDIGITAL": "axtd",
            "AXTD": "axtd",
            "AD": "axtd",
            "P10T": "p10t",
            "PSM1000": "p10t",
        }
        return type_map.get(api_type_upper, "unknown")

    @staticmethod
    def _format_runtime(minutes: int | None) -> str:
        """Format battery runtime from minutes to HH:MM format.

        Args:
            minutes: Battery runtime in minutes

        Returns:
            Formatted runtime string (HH:MM) or empty string if invalid
        """
        if minutes is None or minutes < 0:
            return ""
        try:
            hours = int(minutes) // 60
            mins = int(minutes) % 60
            return f"{hours:02d}:{mins:02d}"
        except (ValueError, TypeError):
            return ""
