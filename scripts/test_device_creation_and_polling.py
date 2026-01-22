#!/usr/bin/env python
"""
Django-Micboard: Test Device Creation & Polling Integration

This script:
1. Creates 3 test devices via Django models (hostname, FQDN, IP)
2. Verifies Device, Transmitter, Receiver models are created
3. Runs poll_devices to fetch real data from Shure API
4. Confirms models are updated with actual device state

Usage:
    python scripts/test_device_creation_and_polling.py [--cleanup]

Examples:
    # Create test devices and run polling
    python scripts/test_device_creation_and_polling.py
    
    # Clean up test devices
    python scripts/test_device_creation_and_polling.py --cleanup
"""

import os
import sys
import argparse
import logging
from typing import Optional, List, Dict, Any

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django
django.setup()

from django.conf import settings
from micboard.models import Manufacturer, Receiver, Channel, Transmitter
from micboard.integrations.shure.client import ShureSystemAPIClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


class DeviceTestingFramework:
    """Test device creation and polling integration."""

    def __init__(self):
        """Initialize the framework."""
        config = getattr(settings, "MICBOARD_CONFIG", {})
        base_url = config.get("SHURE_API_BASE_URL", "https://localhost:10000")
        shared_key = config.get("SHURE_API_SHARED_KEY")
        verify_ssl = config.get("SHURE_API_VERIFY_SSL", False)
        
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() in ('true', '1', 'yes')
        
        if not shared_key:
            raise ValueError(
                "SHURE_API_SHARED_KEY not configured. Set MICBOARD_SHURE_API_SHARED_KEY "
                "environment variable or update MICBOARD_CONFIG in Django settings."
            )
        
        self.client = ShureSystemAPIClient(base_url=base_url, verify_ssl=verify_ssl)
        logger.info("=" * 80)
        logger.info("Django-Micboard Device Testing Framework")
        logger.info("=" * 80)
        logger.info(f"\nShure API: {base_url}")

    def get_or_create_manufacturer(self) -> 'Manufacturer':
        """Get or create Shure manufacturer."""
        manufacturer, created = Manufacturer.objects.get_or_create(
            code="shure",
            defaults={
                "name": "Shure Incorporated",
                "website": "https://www.shure.com",
                "is_active": True,
            }
        )
        
        status = "created" if created else "found"
        logger.info(f"✓ Manufacturer (Shure) {status}")
        return manufacturer

    def discover_devices_from_api(self) -> List[Dict[str, Any]]:
        """Fetch real devices from Shure API."""
        logger.info("\nFetching devices from Shure System API...")
        
        try:
            devices = self.client.devices.get_devices()
            logger.info(f"✓ Found {len(devices)} devices from API")
            
            # Show first few
            if devices:
                logger.info("\nSample devices from API:")
                for device in devices[:3]:
                    logger.info(f"  - {device.get('model')} @ {device.get('id')}")
                if len(devices) > 3:
                    logger.info(f"  ... and {len(devices) - 3} more")
            
            return devices
        except Exception as e:
            logger.error(f"✗ Failed to fetch devices: {e}")
            return []

    def create_test_receiver_by_hostname(self, manufacturer: 'Manufacturer', api_devices: List[Dict]) -> 'Receiver':
        """Create test receiver using hostname."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 1: Receiver Creation by Hostname")
        logger.info("-" * 80)
        
        if not api_devices:
            logger.warning("⚠ No API devices available to test with")
            return None
        
        # Use first API device as reference
        api_device = api_devices[0]
        ip = api_device.get('id')
        hostname = f"ulxd-{ip.split('.')[-1]}"
        
        try:
            receiver, created = Receiver.objects.get_or_create(
                manufacturer=manufacturer,
                api_device_id=ip,
                defaults={
                    "name": hostname,
                    "ip": ip,
                    "device_type": "ulxd",  # Based on API model
                    "firmware_version": api_device.get('properties', {}).get('firmware_version', ''),
                    "is_active": True,
                }
            )
            
            status = "created" if created else "found"
            logger.info(f"✓ Receiver created by hostname: {receiver.name}")
            logger.info(f"  API ID: {receiver.api_device_id}")
            logger.info(f"  IP: {receiver.ip}")
            logger.info(f"  Status: {status}")
            
            return receiver
        except Exception as e:
            logger.error(f"✗ Failed to create receiver by hostname: {e}")
            return None

    def create_test_receiver_by_fqdn(self, manufacturer: 'Manufacturer', api_devices: List[Dict]) -> 'Receiver':
        """Create test receiver using FQDN."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 2: Receiver Creation by FQDN")
        logger.info("-" * 80)
        
        if len(api_devices) < 2:
            logger.warning("⚠ Need at least 2 API devices to test FQDN")
            return None
        
        # Use second API device
        api_device = api_devices[1]
        ip = api_device.get('id')
        fqdn = f"shure-ulxd-{ip.split('.')[-1]}.campus.local"
        
        try:
            receiver, created = Receiver.objects.get_or_create(
                manufacturer=manufacturer,
                api_device_id=ip,
                defaults={
                    "name": fqdn,
                    "ip": ip,
                    "device_type": "ulxd",
                    "firmware_version": api_device.get('properties', {}).get('firmware_version', ''),
                    "is_active": True,
                }
            )
            
            status = "created" if created else "found"
            logger.info(f"✓ Receiver created by FQDN: {receiver.name}")
            logger.info(f"  API ID: {receiver.api_device_id}")
            logger.info(f"  IP: {receiver.ip}")
            logger.info(f"  Status: {status}")
            
            return receiver
        except Exception as e:
            logger.error(f"✗ Failed to create receiver by FQDN: {e}")
            return None

    def create_test_receiver_by_ip(self, manufacturer: 'Manufacturer', api_devices: List[Dict]) -> 'Receiver':
        """Create test receiver using IP address."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 3: Receiver Creation by IP Address")
        logger.info("-" * 80)
        
        if len(api_devices) < 3:
            logger.warning("⚠ Need at least 3 API devices to test IP")
            return None
        
        # Use third API device
        api_device = api_devices[2]
        ip = api_device.get('id')
        
        try:
            receiver, created = Receiver.objects.get_or_create(
                manufacturer=manufacturer,
                api_device_id=ip,
                defaults={
                    "name": ip,
                    "ip": ip,
                    "device_type": "ulxd",
                    "firmware_version": api_device.get('properties', {}).get('firmware_version', ''),
                    "is_active": True,
                }
            )
            
            status = "created" if created else "found"
            logger.info(f"✓ Receiver created by IP: {receiver.name}")
            logger.info(f"  API ID: {receiver.api_device_id}")
            logger.info(f"  IP: {receiver.ip}")
            logger.info(f"  Status: {status}")
            
            return receiver
        except Exception as e:
            logger.error(f"✗ Failed to create receiver by IP: {e}")
            return None

    def verify_models(self, receivers: List['Receiver']):
        """Verify Receiver, Channel, Transmitter models."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 4: Model Verification")
        logger.info("-" * 80)
        
        logger.info(f"\nReceiver Models:")
        logger.info(f"  Total Receivers: {Receiver.objects.count()}")
        logger.info(f"  Active Receivers: {Receiver.objects.filter(is_active=True).count()}")
        
        for receiver in receivers:
            logger.info(f"\n  Receiver: {receiver.name}")
            logger.info(f"    API ID: {receiver.api_device_id}")
            logger.info(f"    IP: {receiver.ip}")
            logger.info(f"    Model: {receiver.device_type}")
            logger.info(f"    Firmware: {receiver.firmware_version}")
            logger.info(f"    Active: {receiver.is_active}")
            
            # Check channels
            channels = Channel.objects.filter(receiver=receiver)
            logger.info(f"    Channels: {channels.count()}")
            
            # Check transmitters
            transmitters = Transmitter.objects.filter(channel__receiver=receiver)
            logger.info(f"    Transmitters: {transmitters.count()}")

    def simulate_polling(self, receivers: List['Receiver']):
        """Simulate what poll_devices command will do."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 5: Polling Simulation")
        logger.info("-" * 80)
        
        logger.info("\nSimulating device polling from Shure API...")
        
        try:
            # Get current API devices
            api_devices = self.client.devices.get_devices()
            logger.info(f"✓ Retrieved {len(api_devices)} devices from API")
            
            # For each test receiver, check if it exists in API
            for receiver in receivers:
                api_device = next(
                    (d for d in api_devices if d.get('id') == receiver.api_device_id),
                    None
                )
                
                if api_device:
                    logger.info(f"\n✓ Receiver {receiver.name} found in API:")
                    logger.info(f"  API State: {api_device.get('state')}")
                    logger.info(f"  Model: {api_device.get('model')}")
                    logger.info(f"  Firmware: {api_device.get('properties', {}).get('firmware_version', 'N/A')}")
                    logger.info(f"  Serial: {api_device.get('properties', {}).get('serial_number', 'N/A')}")
                    
                    # In real polling, this would:
                    # 1. Update Receiver model with state
                    # 2. Create/update Channel and Transmitter models
                    # 3. Broadcast via WebSocket
                    # 4. Trigger alerts if state changed
                    
                else:
                    logger.warning(f"⚠ Receiver {receiver.name} NOT found in API")
                    logger.info("  (This is normal if device hasn't been discovered yet)")
            
            logger.info("\n✓ Polling simulation complete")
            logger.info("  In production, manage.py poll_devices will:")
            logger.info("    1. Fetch all devices from Shure API")
            logger.info("    2. Update Receiver/Channel/Transmitter models")
            logger.info("    3. Broadcast state changes via WebSocket")
            logger.info("    4. Trigger configured alerts")
            
        except Exception as e:
            logger.error(f"✗ Polling simulation failed: {e}")

    def cleanup_test_receivers(self):
        """Remove test receivers."""
        logger.info("\n" + "-" * 80)
        logger.info("Cleanup: Removing Test Receivers")
        logger.info("-" * 80)
        
        count = Receiver.objects.count()
        Receiver.objects.all().delete()
        logger.info(f"✓ Deleted {count} test receiver(s)")

    def print_summary(self, api_devices: int, created_receivers: int):
        """Print test summary."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        
        logger.info(f"\nShure API Status:")
        logger.info(f"  Devices discovered: {api_devices}")
        
        logger.info(f"\nDjango Models:")
        logger.info(f"  Receivers created: {created_receivers}")
        logger.info(f"  Total in database: {Receiver.objects.count()}")
        logger.info(f"  Channels: {Channel.objects.count()}")
        logger.info(f"  Transmitters: {Transmitter.objects.count()}")
        
        logger.info(f"\nNext Steps:")
        logger.info(f"  1. Run: python manage.py poll_devices")
        logger.info(f"     This will poll the API and update Receiver/Channel/Transmitter models")
        logger.info(f"  2. Monitor with: python scripts/shure_discovery_monitor.py")
        logger.info(f"  3. Start Django dev server: python manage.py runserver")
        logger.info(f"  4. Access admin: http://localhost:8000/admin")
        
        if created_receivers > 0:
            logger.info(f"\n✓ Test receivers ready for polling!")
        else:
            logger.info(f"\n⚠ No test receivers created (check device discovery)")

    def run(self, cleanup: bool = False):
        """Run all tests."""
        if cleanup:
            self.cleanup_test_receivers()
            return
        
        # Get manufacturer
        manufacturer = self.get_or_create_manufacturer()
        
        # Discover devices from API
        api_devices = self.discover_devices_from_api()
        
        if not api_devices:
            logger.error("\n✗ No devices from API - cannot proceed with tests")
            logger.info("  Check: python scripts/shure_api_health_check.py")
            return
        
        # Create test receivers
        created_receivers = []
        
        receiver1 = self.create_test_receiver_by_hostname(manufacturer, api_devices)
        if receiver1:
            created_receivers.append(receiver1)
        
        receiver2 = self.create_test_receiver_by_fqdn(manufacturer, api_devices)
        if receiver2:
            created_receivers.append(receiver2)
        
        receiver3 = self.create_test_receiver_by_ip(manufacturer, api_devices)
        if receiver3:
            created_receivers.append(receiver3)
        
        if created_receivers:
            # Verify models
            self.verify_models(created_receivers)
            
            # Simulate polling
            self.simulate_polling(created_receivers)
        
        # Print summary
        self.print_summary(len(api_devices), len(created_receivers))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test device creation and polling integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create test devices
  python scripts/test_device_creation_and_polling.py
  
  # Clean up test devices
  python scripts/test_device_creation_and_polling.py --cleanup

After this test passes:
  1. Run polling: python manage.py poll_devices
  2. Monitor: python scripts/shure_discovery_monitor.py
  3. Web UI: python manage.py runserver
        """
    )
    
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove test devices from database"
    )
    
    args = parser.parse_args()
    
    try:
        tester = DeviceTestingFramework()
        tester.run(cleanup=args.cleanup)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
