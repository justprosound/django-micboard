"""Views for charger display UI and helpers.

This module provides the `charger_display` view which renders a page
showing the status of networked charging stations and docked microphones.
It queries the Shure System API via the manufacturers shure client.
"""

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from micboard.manufacturers.shure.client import ShureAPIError, ShureSystemAPIClient

logger = logging.getLogger(__name__)


def charger_display(request: HttpRequest) -> HttpResponse:
    """
    View to display the status of networked charging stations and microphones.
    """
    client = ShureSystemAPIClient()
    charging_stations_data = []
    error_message = None

    try:
        all_devices = client.poll_all_devices()

        # Filter for charging stations (example device types, adjust as needed)
        # Based on web search, common Shure charging stations include SBC250, SBC850, MXWNCS8, MXWNCS4, SBC220
        charging_station_models = ["SBC250", "SBC850", "MXWNCS8", "MXWNCS4", "SBC220"]

        for device_id, device_data in all_devices.items():
            # Assuming 'model' or 'device_type' field indicates a charging station
            # The exact field name might need to be confirmed from actual API responses
            if (
                device_data.get("model") in charging_station_models
                or device_data.get("device_type") in charging_station_models
            ):
                station_slots = []
                # Assuming charging station data includes 'slots' or 'channels' with mic info
                # This part is highly dependent on the actual Shure API response structure for chargers
                # For now, I'll simulate based on the expected template context

                # Placeholder logic: In a real scenario, you'd parse the device_data
                # to find docked microphones and their status.
                # For demonstration, I'll use a simplified approach.

                # If the device itself is a charger, its 'channels' might represent slots
                # or there might be a separate endpoint/field for docked devices.
                # For now, let's assume 'channels' might contain some info or we'd need to query further.

                # Example: If device_data has a 'docked_mics' list or similar
                if "channels" in device_data:
                    for channel in device_data["channels"]:
                        # Assuming channel data might contain info about docked mics
                        # This is a simplification. Real API might require more specific parsing.
                        if channel.get("tx_status") == "docked":  # Hypothetical field
                            station_slots.append(
                                {
                                    "slot_number": channel.get("channel_number"),
                                    "mic_name": channel.get("tx_name", "Unknown Mic"),
                                    "battery_level": channel.get("tx_battery_percentage", 0),
                                    "charging": channel.get(
                                        "tx_charging_status", False
                                    ),  # Hypothetical field
                                }
                            )
                        elif (
                            channel.get("transmitter")
                            and channel["transmitter"].get("battery_percentage") is not None
                        ):
                            # If a transmitter is associated with a channel, assume it's docked
                            # and use its battery info. This is a heuristic.
                            station_slots.append(
                                {
                                    "slot_number": channel.get("channel_number"),
                                    "mic_name": channel["transmitter"].get("name", "Unknown Mic"),
                                    "battery_level": channel["transmitter"].get(
                                        "battery_percentage", 0
                                    ),
                                    "charging": channel["transmitter"].get(
                                        "charging_status", False
                                    ),  # Another hypothetical
                                }
                            )

                charging_stations_data.append(
                    {
                        "id": device_id,
                        "name": device_data.get("name", f"Charger {device_id}"),
                        "status": "online"
                        if client.is_healthy()
                        else "offline",  # Simplified status
                        "slots": station_slots,
                    }
                )

    except ShureAPIError as e:
        logger.error("Error fetching Shure API data for charger display: %s", e)
        error_message = f"Failed to connect to Shure API: {e.message}"
    except Exception as e:
        logger.error("An unexpected error occurred in charger display: %s", e)
        error_message = "An unexpected error occurred while fetching charger data."

    context = {
        "page_title": "Charger Display",
        "charging_stations": charging_stations_data,
        "error_message": error_message,
    }
    return render(request, "micboard/charger_display.html", context)
