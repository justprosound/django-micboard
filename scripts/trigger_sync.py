#!/usr/bin/env python
"""Quick script to trigger discovery sync for testing."""

import os
import sys

import django

# Setup Django
sys.path.insert(0, "/home/skuonen/django-micboard")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
django.setup()

from micboard.models import DiscoveredDevice, Manufacturer
from micboard.tasks.discovery_tasks import run_discovery_sync_task

# Show what we have
print("=== Current State ===")
shure = Manufacturer.objects.get(code="shure")
devices = DiscoveredDevice.objects.filter(manufacturer=shure)
print(f"Manufacturer: {shure.name}")
print(f"DiscoveredDevices in Django: {devices.count()}")
for dev in devices:
    print(f"  - {dev.ip}")

# Run the sync
print("\n=== Running Discovery Sync ===")
result = run_discovery_sync_task(
    manufacturer_id=shure.id,
    scan_cidrs=False,
    scan_fqdns=False,
    max_hosts=1024,
)

# Show results
print(f"\nStatus: {result.get('status')}")
print(f"Created receivers: {result.get('created_receivers', 0)}")
print(f"Missing IPs submitted: {result.get('missing_ips_submitted', 0)}")
print(f"Scanned IPs submitted: {result.get('scanned_ips_submitted', 0)}")
if result.get("errors"):
    print("Errors:")
    for error in result["errors"]:
        print(f"  - {error}")
