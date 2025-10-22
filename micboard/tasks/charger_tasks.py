import logging

from django.core.cache import cache

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


def poll_charger_data(manufacturer_id: int):
    """
    Task to poll charger data from a specific manufacturer's API.
    """
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        all_devices = plugin.get_devices()  # list of dicts

        charging_stations_data = []
        charging_station_models = ["SBC250", "SBC850", "MXWNCS8", "MXWNCS4", "SBC220"]

        for device_data in all_devices:
            device_id = device_data.get("api_device_id")
            if (
                device_id is not None
                and isinstance(device_id, str)
                and (
                    device_data.get("model") in charging_station_models
                    or device_data.get("device_type") in charging_station_models
                )
            ):
                station_slots = []
                # Get channels for this charger
                try:
                    channels = plugin.get_device_channels(device_id)
                    for channel in channels:
                        tx_data = channel.get("tx")
                        if tx_data:
                            station_slots.append(
                                {
                                    "slot_number": channel.get("channel", 0),
                                    "mic_name": tx_data.get("name", "Unknown Mic"),
                                    "battery_level": tx_data.get("battery_percentage", 0),
                                    "charging": tx_data.get("charging_status", False),
                                }
                            )
                except Exception:
                    # If no channels, empty slots
                    pass

                charging_stations_data.append(
                    {
                        "id": device_id,
                        "name": device_data.get("name", f"Charger {device_id}"),
                        "status": "online" if plugin.get_client().is_healthy() else "offline",
                        "slots": station_slots,
                    }
                )
        # Cache the data
        cache.set(f"charger_data_{manufacturer.code}", charging_stations_data, timeout=60)

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found for charger polling task.", manufacturer_id
        )
    except Exception as e:
        logger.exception(
            "Error polling charger data for manufacturer ID %s: %s", manufacturer_id, e
        )
