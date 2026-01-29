#!/usr/bin/env python
"""Run discovery (API only, no network scanning)."""

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

import logging

from micboard.models import DiscoveryQueue, Manufacturer
from micboard.tasks.discovery_tasks import run_discovery_sync_task

# Reduce logging noise
logging.getLogger("urllib3").setLevel(logging.ERROR)

# Get Shure manufacturer
manufacturer = Manufacturer.objects.get(code="shure")


# Run discovery sync WITHOUT scanning (just pull from API)
result = run_discovery_sync_task(
    manufacturer_id=manufacturer.id,
    add_cidrs=None,
    add_fqdns=None,
    scan_cidrs=False,  # Don't scan CIDR
    scan_fqdns=False,  # Don't scan FQDN
    max_hosts=1024,
)


if result.get("errors"):
    pass

# Check what was discovered
queue_items = DiscoveryQueue.objects.filter(manufacturer=manufacturer)

# Group by device type
for device_type in ["charger", "receiver", "transmitter", "transceiver"]:
    count = queue_items.filter(device_type=device_type).count()
    if count > 0:
        pass

# Show some examples
for _i, item in enumerate(queue_items[:10], 1):
    fqdn = "?"
    try:
        import socket

        fqdn = socket.getfqdn(item.ip)
    except Exception:
        pass
