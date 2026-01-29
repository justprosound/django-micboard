#!/usr/bin/env python
"""Check what devices are available from Shure API."""

import os
import sys

import django

# Get Shure shared key from Windows
if os.path.exists("/mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt"):
    with open("/mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt", "r") as f:
        shared_key = f.read().strip()
        os.environ["MICBOARD_SHURE_API_SHARED_KEY"] = shared_key

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from micboard.integrations.shure.plugin import ShurePlugin
from micboard.models import Manufacturer

manufacturer = Manufacturer.objects.get(code="shure")
plugin = ShurePlugin(manufacturer)
client = plugin.get_client()

# Get devices
devices = client.get_devices()

for _i, dev in enumerate(devices[:3]):
    pass

# Check which devices have serial numbers
devices_with_serial = 0
devices_without_serial = 0

for dev in devices:
    if dev.get("serialNumber"):
        devices_with_serial += 1
    else:
        devices_without_serial += 1


# Try to get device details for a device
if devices:
    first_device = devices[0]
    device_id = first_device.get("id")
    if device_id:
        try:
            # Try to fetch device identity to get serial
            identity = client.devices.get_device_identity(device_id)
        except Exception:
            pass
