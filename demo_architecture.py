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

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import DiscoveredDevice, Manufacturer, WirelessChassis
from micboard.services.hardware_deduplication_service import get_hardware_deduplication_service
from micboard.services.manufacturer import ManufacturerService


def print_section(title):
    """Print a section header."""


def demo_plugin_system():
    """Demonstrate the plugin system."""
    print_section("1. PLUGIN SYSTEM - Manufacturer Agnostic")

    # Get all active manufacturers
    manufacturers = Manufacturer.objects.filter(is_active=True)

    for mfg in manufacturers:
        try:
            # Get plugin for this manufacturer
            plugin_class = get_manufacturer_plugin(mfg.code)
            plugin = plugin_class(mfg)

            # Check capabilities
            capabilities = []
            if hasattr(plugin, "get_devices"):
                capabilities.append("✓ get_devices()")
            if hasattr(plugin, "add_discovery_ips"):
                capabilities.append("✓ add_discovery_ips()")
            if hasattr(plugin, "transform_device_data"):
                capabilities.append("✓ transform_device_data()")
            if hasattr(plugin, "is_healthy"):
                capabilities.append("✓ is_healthy()")

            # Check health
            try:
                plugin.is_healthy()
            except Exception:
                pass

        except Exception:
            pass


def demo_device_sync():
    """Demonstrate device synchronization."""
    print_section("2. DEVICE SYNC - Same Code for All Manufacturers")

    manufacturers = Manufacturer.objects.filter(is_active=True)[:2]  # Test first 2

    for mfg in manufacturers:
        try:
            # This SAME code works for ANY manufacturer!
            result = ManufacturerService.sync_devices_for_manufacturer(manufacturer_code=mfg.code)

            if result["success"]:
                pass
            else:
                pass

        except Exception:
            pass


def demo_discovered_devices():
    """Show discovered devices with manufacturer-specific metadata."""
    print_section("3. DISCOVERED DEVICES - Generic + Metadata")

    discovered = DiscoveredDevice.objects.all()[:5]

    for device in discovered:
        # Show manufacturer-specific metadata
        if device.metadata:
            # Shure-specific
            if "compatibility" in device.metadata:
                pass


def demo_deduplication():
    """Demonstrate deduplication system."""
    print_section("4. DEDUPLICATION - Prevent Duplicates")

    # Get a manufacturer
    mfg = Manufacturer.objects.filter(is_active=True).first()
    if not mfg:
        return

    # Get deduplication service
    dedup_service = get_hardware_deduplication_service(mfg)

    # Simulate checking a device

    result = dedup_service.check_device(
        serial_number="TEST-SERIAL-12345",
        mac_address="00:11:22:33:44:55",
        ip="192.168.1.100",
        api_device_id="test-device-001",
        manufacturer=mfg,
    )

    if result.existing_device:
        pass
    if hasattr(result, "conflict_reason") and result.conflict_reason:
        pass


def demo_wireless_chassis():
    """Show wireless chassis devices."""
    print_section("5. WIRELESS CHASSIS - Manufacturer Agnostic Models")

    chassis = WirelessChassis.objects.select_related("manufacturer")[:5]

    for device in chassis:
        # These fields work for ANY manufacturer!
        if hasattr(device, "battery_health"):
            pass


def demo_bi_directional_sync():
    """Explain bi-directional sync."""
    print_section("6. BI-DIRECTIONAL SYNC - Admin ↔ API")


def main():
    """Run all demonstrations."""
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
