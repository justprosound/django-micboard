#!/usr/bin/env python
"""Demonstration of django-micboard's manufacturer-agnostic architecture.

This script shows:
1. How the plugin system works
2. How to sync devices from different manufacturers
3. How deduplication prevents duplicates
4. How bi-directional sync keeps admin and APIs in sync
"""

import os
import sys

import django

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import DiscoveredDevice, Manufacturer, WirelessChassis
from micboard.services.manufacturer.manufacturer import ManufacturerService
from micboard.services.sync.hardware_deduplication_service import (
    get_hardware_deduplication_service,
)


def print_section(title):
    """Print a section header."""


# ... other demo functions stay mostly the same ...
def demo_plugin_system():
    print_section("1. PLUGIN SYSTEM - Manufacturer Agnostic")
    manufacturers = Manufacturer.objects.filter(is_active=True)
    for mfg in manufacturers:
        try:
            plugin_class = get_manufacturer_plugin(mfg.code)
            plugin = plugin_class(mfg)
            capabilities = []
            if hasattr(plugin, "get_devices"):
                capabilities.append("✓ get_devices()")
            if hasattr(plugin, "add_discovery_ips"):
                capabilities.append("✓ add_discovery_ips()")
            if hasattr(plugin, "transform_device_data"):
                capabilities.append("✓ transform_device_data()")
            if hasattr(plugin, "is_healthy"):
                capabilities.append("✓ is_healthy()")
            try:
                plugin.is_healthy()
            except Exception:
                pass
        except Exception:
            pass


def demo_device_sync():
    print_section("2. DEVICE SYNC - Same Code for All Manufacturers")
    manufacturers = Manufacturer.objects.filter(is_active=True)[:2]
    for mfg in manufacturers:
        try:
            result = ManufacturerService.sync_devices_for_manufacturer(manufacturer_code=mfg.code)
            if result["success"]:
                pass
            else:
                pass
        except Exception:
            pass


def demo_discovered_devices():
    print_section("3. DISCOVERED DEVICES - Generic + Metadata")
    discovered = DiscoveredDevice.objects.all()[:5]
    for device in discovered:
        if device.metadata and "compatibility" in device.metadata:
            pass


def demo_deduplication():
    print_section("4. DEDUPLICATION - Prevent Duplicates")
    mfg = Manufacturer.objects.filter(is_active=True).first()
    if not mfg:
        return
    dedup_service = get_hardware_deduplication_service(mfg)
    result = dedup_service.check_device(
        serial_number="TEST-SERIAL-12345",
        mac_address="00:11:22:33:44:55",
        ip="192.168.1.100",
        api_device_id="test-device-001",
        manufacturer=mfg,
    )
    if getattr(result, "existing_device", None):
        pass
    if hasattr(result, "conflict_reason") and getattr(result, "conflict_reason", None):
        pass


def demo_wireless_chassis():
    print_section("5. WIRELESS CHASSIS - Manufacturer Agnostic Models")
    chassis = WirelessChassis.objects.select_related("manufacturer")[:5]
    for device in chassis:
        if hasattr(device, "battery_health"):
            pass


def demo_bi_directional_sync():
    print_section("6. BI-DIRECTIONAL SYNC - Admin ↔ API")


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
    sys.path.insert(0, os.path.dirname(__file__))
    django.setup()
    try:
        demo_plugin_system()
        demo_device_sync()
        demo_discovered_devices()
        demo_deduplication()
        demo_wireless_chassis()
        demo_bi_directional_sync()
        print_section("SUMMARY")
    except KeyboardInterrupt:
        pass
    except Exception:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
