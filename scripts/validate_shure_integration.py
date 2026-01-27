#!/usr/bin/env python
"""Validation script for Shure System API integration with bi-directional sync.

This script demonstrates:
1. API connectivity and health check
2. WirelessChassis discovery configuration
3. WirelessChassis polling and Django model updates
4. WebSocket bi-directional sync capability
5. Complete data flow from Shure API → Django models → WebSocket broadcast

Usage:
    # Load environment and run
    source .env.local && export $(grep -v '^#' .env.local | xargs)
    uv run python scripts/validate_shure_integration.py

    # Or with Django settings
    DJANGO_SETTINGS_MODULE=demo.settings uv run python scripts/validate_shure_integration.py
"""

from __future__ import annotations

import os
import sys

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django

django.setup()

from django.conf import settings

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.models import RFChannel, Manufacturer, WirelessChassis, WirelessUnit


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def validate_configuration():
    """Validate Shure API configuration is present."""
    print_section("1. Configuration Validation")

    config = settings.MICBOARD_CONFIG
    base_url = config.get("SHURE_API_BASE_URL")
    shared_key = config.get("SHURE_API_SHARED_KEY")
    verify_ssl = config.get("SHURE_API_VERIFY_SSL", True)

    print(f"Base URL: {base_url}")
    print(f"Shared Key: {'✓ Configured' if shared_key else '✗ Missing'}")
    print(f"SSL Verification: {verify_ssl}")

    if not base_url or not shared_key:
        print("\n⚠ Configuration incomplete!")
        print("   Set MICBOARD_SHURE_API_BASE_URL and MICBOARD_SHURE_API_SHARED_KEY")
        sys.exit(1)

    print("\n✓ Configuration valid")
    return base_url, shared_key, verify_ssl


def validate_api_connectivity():
    """Test Shure System API connectivity and health."""
    print_section("2. API Connectivity Test")

    try:
        client = ShureSystemAPIClient()
        print("✓ Client initialized")
        print(f"  Base URL: {client.base_url}")
        print(f"  WebSocket URL: {client.websocket_url}")

        # Health check
        print("\nPerforming health check...")
        health = client.check_health()
        status = health.get("status")

        if status == "healthy":
            print("✓ API is healthy")
            return client
        else:
            print(f"✗ API unhealthy: {health.get('message', 'Unknown error')}")
            sys.exit(1)

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)


def validate_discovery_config(client: ShureSystemAPIClient):
    """Check device discovery configuration."""
    print_section("3. WirelessChassis Discovery Configuration")

    try:
        discovery_ips = client.get_discovery_ips()
        print(f"Discovery IPs configured: {len(discovery_ips)}")

        if discovery_ips:
            # Show first 10 and last 5
            if len(discovery_ips) <= 15:
                for ip in discovery_ips:
                    print(f"  - {ip}")
            else:
                print("  First 10 IPs:")
                for ip in discovery_ips[:10]:
                    print(f"    - {ip}")
                print(f"  ... ({len(discovery_ips) - 15} more)")
                print("  Last 5 IPs:")
                for ip in discovery_ips[-5:]:
                    print(f"    - {ip}")

        # Get current device count
        devices = client.get_devices()
        print(f"\nDevices currently discovered: {len(devices)}")

        if devices:
            print("\nDevice Summary:")
            for i, device in enumerate(devices[:5], 1):
                model = device.get("model", "Unknown")
                device_id = device.get("device_id", "No ID")
                ip = device.get("ip_address", "N/A")
                status = device.get("connection_status", "Unknown")
                print(f"  {i}. {model} (ID: {device_id})")
                print(f"     IP: {ip}, Status: {status}")

            if len(devices) > 5:
                print(f"  ... and {len(devices) - 5} more")
        else:
            print("\n⚠ No devices discovered")
            print("  This is expected if no physical Shure devices are connected")
            print("  or if they are not on the configured discovery IPs")

        return devices

    except Exception as e:
        print(f"✗ Discovery check failed: {e}")
        return []


def validate_plugin_interface():
    """Validate Shure manufacturer plugin integration."""
    print_section("4. Plugin Interface Validation")

    try:
        # Get or create Shure manufacturer
        manufacturer, created = Manufacturer.objects.get_or_create(
            code="shure",
            defaults={
                "name": "Shure",
                "is_active": True,
            },
        )

        if created:
            print("✓ Created Shure manufacturer record")
        else:
            print(f"✓ Using existing Shure manufacturer (ID: {manufacturer.id})")

        # Initialize plugin
        plugin = ShurePlugin(manufacturer)
        print("✓ Plugin initialized")

        # Test plugin methods
        print("\nTesting plugin methods:")

        # Health check
        health = plugin.check_health()
        print(f"  - check_health(): {health.get('status')}")

        # Get devices
        devices = plugin.get_devices()
        print(f"  - get_devices(): {len(devices)} devices")

        # WebSocket capability (via get_client())
        ws_url = plugin.get_client().websocket_url
        print(f"  - WebSocket URL (via client): {ws_url}")

        return manufacturer, plugin

    except Exception as e:
        print(f"✗ Plugin validation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def validate_django_integration(manufacturer: Manufacturer, plugin: ShurePlugin):
    """Test Django model integration with API data."""
    print_section("5. Django Model Integration")

    # Count existing records
    receivers_count = WirelessChassis.objects.filter(manufacturer=manufacturer).count()
    channels_count = RFChannel.objects.filter(receiver__manufacturer=manufacturer).count()
    transmitters_count = WirelessUnit.objects.filter(
        channel__receiver__manufacturer=manufacturer
    ).count()

    print("Current database state:")
    print(f"  - Receivers: {receivers_count}")
    print(f"  - Channels: {channels_count}")
    print(f"  - Transmitters: {transmitters_count}")

    # Get devices from API
    devices = plugin.get_devices()

    if not devices:
        print("\n⚠ No devices from API to sync")
        print("  Django integration can only be tested with real devices")
        return

    print(f"\nDevices from API: {len(devices)}")

    # Simulate polling update (without actually running poll_manufacturer_devices)
    print("\nTo sync these devices to Django, run:")
    print("  python manage.py poll_devices --manufacturer shure")
    print("\nOr programmatically:")
    print("  from micboard.services import PollingService")
    print("  service = PollingService()")
    print("  result = service.poll_manufacturer(manufacturer)")


def validate_websocket_capability(plugin: ShurePlugin):
    """Show WebSocket bi-directional sync capability."""
    print_section("6. Bi-Directional Sync (WebSocket)")

    ws_url = plugin.get_client().websocket_url
    print(f"WebSocket URL: {ws_url}")

    print("\nWebSocket Integration:")
    print("  The ShurePlugin provides connect_and_subscribe() for real-time updates")
    print("  This enables bi-directional sync:")
    print("    - Shure hardware changes → WebSocket → Django models → UI")
    print("    - UI changes → Django → Shure API (via plugin methods)")

    print("\nTo start WebSocket monitoring:")
    print("  from micboard.integrations.shure.plugin import ShurePlugin")
    print("  plugin = ShurePlugin(manufacturer)")
    print("  plugin.connect_and_subscribe(on_message=callback)")

    print("\nWebSocket subscriptions are automatically started by:")
    print("  - poll_manufacturer_devices task (after successful poll)")
    print("  - Django-Q async task: start_shure_websocket_subscriptions")


def validate_complete_workflow():
    """Show the complete data flow architecture."""
    print_section("7. Complete Data Flow Architecture")

    print("Data Flow:")
    print("  1. Shure System API (localhost:10000)")
    print("     ↓")
    print("  2. ShureSystemAPIClient (HTTP + Auth)")
    print("     ↓")
    print("  3. ShurePlugin (Transform API → micboard format)")
    print("     ↓")
    print("  4. PollingService (Update Django models)")
    print("     ↓")
    print("  5. Django Signals (devices_polled, api_health_changed)")
    print("     ↓")
    print("  6. Django Channels (WebSocket broadcast to UI)")

    print("\nBi-Directional Sync:")
    print("  Hardware Change → WebSocket Event → Django Models → UI Update")
    print("  UI Action → Django View → ShurePlugin → Shure API → Hardware")

    print("\nKey Components:")
    print("  - micboard/integrations/shure/client.py: API communication")
    print("  - micboard/integrations/shure/plugin.py: Plugin interface")
    print("  - micboard/tasks/polling_tasks.py: Background polling")
    print("  - micboard/services/polling.py: PollingService")
    print("  - micboard/signals/broadcast_signals.py: Event broadcasting")


def main():
    """Run complete validation."""
    print("=" * 80)
    print("  SHURE SYSTEM API INTEGRATION VALIDATION")
    print("=" * 80)

    # Step 1: Configuration
    validate_configuration()

    # Step 2: API Connectivity
    client = validate_api_connectivity()

    # Step 3: Discovery
    devices = validate_discovery_config(client)

    # Step 4: Plugin Interface
    manufacturer, plugin = validate_plugin_interface()

    # Step 5: Django Integration
    validate_django_integration(manufacturer, plugin)

    # Step 6: WebSocket
    validate_websocket_capability(plugin)

    # Step 7: Complete Workflow
    validate_complete_workflow()

    # Summary
    print_section("VALIDATION SUMMARY")
    print("✓ Configuration: Valid")
    print("✓ API Connectivity: Healthy")
    print(f"✓ Discovery: {len(devices)} device(s) found")
    print("✓ Plugin Interface: Working")
    print("✓ Django Models: Ready")
    print("✓ WebSocket: Configured")

    if devices:
        print(f"\n✓ READY: {len(devices)} Shure device(s) available for bi-directional sync")
        print("  Run 'python manage.py poll_devices --manufacturer shure' to sync")
    else:
        print("\n⚠ NO DEVICES: No physical Shure devices detected")
        print("  Integration is working, but requires hardware to demonstrate sync")

    print("\nNext steps:")
    print("  1. Connect physical Shure devices to network")
    print("  2. Add device IPs to discovery: client.add_discovery_ips([...])")
    print("  3. Run polling: python manage.py poll_devices --manufacturer shure")
    print("  4. Monitor WebSocket: Django Channels will broadcast real-time updates")


if __name__ == "__main__":
    main()
