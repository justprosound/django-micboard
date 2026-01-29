#!/usr/bin/env python
"""Approve and import discovered devices into WirelessChassis/Charger models."""

import os
import sys

import django
from django.utils import timezone

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from django.contrib.auth.models import User

from micboard.models import Charger, DiscoveryQueue, Location, Manufacturer, WirelessChassis

# Get Shure manufacturer
manufacturer = Manufacturer.objects.get(code="shure")

# Get or create a superuser for importing
try:
    user = User.objects.get(username="admin")
except User.DoesNotExist:
    user = User.objects.create_superuser("admin", "admin@example.com", "admin")

# Get or create default location
try:
    location = Location.objects.first()
    if not location:
        raise Location.DoesNotExist
except (Location.DoesNotExist, AttributeError):
    # Try creating via raw
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO micboard_location (name, building_id) VALUES ('Default', 1)")
    location = Location.objects.first()
    if not location:
        # Just try to use first building
        from micboard.models import Building

        building = Building.objects.first()
        if building:
            location = Location.objects.create(name="Default", building=building)
        else:
            sys.exit(1)


# Get pending items
pending_items = DiscoveryQueue.objects.filter(manufacturer=manufacturer, status="pending")


count = 0
for item in pending_items:
    try:
        if item.device_type == "charger":
            # Create/Update Charger
            charger, created = Charger.objects.update_or_create(
                serial_number=item.serial_number,
                defaults={
                    "manufacturer": item.manufacturer,
                    "ip": item.ip,
                    "name": item.name,
                    "model": item.model,
                    "firmware_version": item.firmware_version,
                    "status": "online",
                    "is_active": True,
                    "device_type": "charger",
                    "location": location,
                },
            )
            item.existing_charger = charger
            action = "created" if created else "updated"
        else:
            # Create/Update WirelessChassis
            receiver, created = WirelessChassis.objects.update_or_create(
                serial_number=item.serial_number,
                defaults={
                    "manufacturer": item.manufacturer,
                    "api_device_id": item.api_device_id,
                    "ip": item.ip,
                    "name": item.name,
                    "model": item.model,
                    "role": item.device_type,  # Map device_type to role
                    "firmware_version": item.firmware_version,
                    "is_online": True,
                    "status": "online",
                },
            )
            item.existing_device = receiver
            action = "created" if created else "updated"

        # Update discovery queue status
        item.status = "imported"
        item.reviewed_at = timezone.now()
        item.reviewed_by = user
        item.save()
        count += 1
    except Exception:
        pass


# Summary
wireless_count = WirelessChassis.objects.filter(manufacturer=manufacturer).count()
charger_count = Charger.objects.filter(manufacturer=manufacturer).count()


for _chassis in WirelessChassis.objects.filter(manufacturer=manufacturer)[:5]:
    pass

for _charger in Charger.objects.filter(manufacturer=manufacturer)[:5]:
    pass
