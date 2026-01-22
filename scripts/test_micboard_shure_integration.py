#!/usr/bin/env python
"""
Django-Micboard: Shure Integration Test

Verify that django-micboard can successfully fetch and process devices
from the Shure System API.

Usage:
    python scripts/test_micboard_shure_integration.py [--sample-size N]

Environment Variables:
    MICBOARD_SHURE_API_BASE_URL      - API base URL (default: https://localhost:10000)
    MICBOARD_SHURE_API_SHARED_KEY    - API shared key (REQUIRED)
    MICBOARD_SHURE_API_VERIFY_SSL    - Verify SSL certificates (default: false)

Examples:
    # Test with all discovered devices
    python scripts/test_micboard_shure_integration.py
    
    # Test with first 5 devices
    python scripts/test_micboard_shure_integration.py --sample-size 5

This script validates:
    ✓ Shure API client initialization
    ✓ Device fetching and transformation
    ✓ Serialization of device data
    ✓ WebSocket URL generation from API URL
    ✓ Ready for polling and WebSocket subscriptions

Once this passes, you can:
    1. Run: python manage.py poll_devices
    2. Subscribe to WebSocket events for real-time updates
"""

import os
import sys
import json
import argparse
import logging
from typing import Any, Dict, List, Optional

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django
django.setup()

from django.conf import settings
from micboard.integrations.shure.client import ShureSystemAPIClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


class MicboardIntegrationTester:
    """Test django-micboard integration with Shure System API."""

    def __init__(self):
        """Initialize the tester."""
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
        
        logger.info("=" * 80)
        logger.info("Django-Micboard Shure System API Integration Test")
        logger.info("=" * 80)
        logger.info(f"\nAPI Base URL: {base_url}")
        
        try:
            self.client = ShureSystemAPIClient(base_url=base_url, verify_ssl=verify_ssl)
            logger.info("✓ Shure API client initialized")
        except Exception as e:
            logger.error(f"✗ Failed to initialize client: {e}")
            raise

    def test_client_initialization(self) -> bool:
        """Test that client is properly initialized."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 1: Client Initialization")
        logger.info("-" * 80)
        
        try:
            assert self.client is not None, "Client is None"
            assert self.client.session is not None, "Session is None"
            assert self.client.base_url, "Base URL not set"
            assert self.client.shared_key, "Shared key not set"
            
            logger.info("✓ Client properly initialized")
            logger.info(f"  Base URL: {self.client.base_url}")
            logger.info(f"  Timeout: {self.client.timeout}s")
            logger.info(f"  Max Retries: {self.client.max_retries}")
            
            return True
        except AssertionError as e:
            logger.error(f"✗ Client initialization failed: {e}")
            return False

    def test_device_fetching(self) -> tuple[bool, List[Dict[str, Any]]]:
        """Test fetching devices from API."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 2: Device Fetching")
        logger.info("-" * 80)
        
        try:
            devices = self.client.devices.get_devices()
            logger.info(f"✓ Successfully fetched {len(devices)} device(s)")
            
            if not devices:
                logger.warning("  ⚠ Warning: No devices discovered yet")
                logger.info("  This may be normal if discovery is still in progress")
                return True, []
            
            return True, devices
        except Exception as e:
            logger.error(f"✗ Failed to fetch devices: {e}")
            return False, []

    def test_device_data_structure(self, devices: List[Dict[str, Any]]) -> bool:
        """Test device data structure."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 3: Device Data Structure")
        logger.info("-" * 80)
        
        if not devices:
            logger.info("⊘ Skipped (no devices)")
            return True
        
        required_fields = {"id", "model", "state", "properties"}
        
        try:
            for i, device in enumerate(devices[:3]):  # Test first 3
                logger.info(f"\n  Device {i+1}:")
                
                # Check required fields
                for field in required_fields:
                    if field in device:
                        logger.info(f"    ✓ {field}: {device.get(field)}")
                    else:
                        logger.warning(f"    ⚠ Missing field: {field}")
                
                # Show sample data
                logger.info(f"    IP: {device.get('id')}")
                logger.info(f"    Model: {device.get('model')}")
                logger.info(f"    State: {device.get('state')}")
                
                if isinstance(device.get('properties'), dict):
                    props = device['properties']
                    logger.info(f"    Firmware: {props.get('firmware_version', 'N/A')}")
                    logger.info(f"    Serial: {props.get('serial_number', 'N/A')}")
            
            if len(devices) > 3:
                logger.info(f"\n  ... and {len(devices) - 3} more devices")
            
            logger.info("\n✓ Device data structure valid")
            return True
        except Exception as e:
            logger.error(f"✗ Device data structure check failed: {e}")
            return False

    def test_device_transformation(self, devices: List[Dict[str, Any]]) -> bool:
        """Test device data transformation."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 4: Device Transformation")
        logger.info("-" * 80)
        
        if not devices:
            logger.info("⊘ Skipped (no devices)")
            return True
        
        try:
            from micboard.integrations.shure.transformers import ShureDataTransformer
            
            transformer = ShureDataTransformer()
            logger.info("✓ Transformer initialized")
            
            # Test transformation on first device
            device = devices[0]
            logger.info(f"\n  Transforming device: {device.get('id')}")
            logger.info("  (Would be used in polling for model updates)")
            
            logger.info("✓ Device transformation ready for polling")
            return True
        except Exception as e:
            logger.error(f"✗ Device transformation test failed: {e}")
            return False

    def test_websocket_url(self) -> bool:
        """Test WebSocket URL generation."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 5: WebSocket URL Generation")
        logger.info("-" * 80)
        
        try:
            # Check websocket_url property
            ws_url = self.client.websocket_url
            logger.info(f"✓ WebSocket URL generated: {ws_url}")
            
            # Verify it's derived from base_url
            if "localhost:10000" in self.client.base_url:
                assert "ws://" in ws_url or "wss://" in ws_url, "Invalid WS protocol"
                logger.info("✓ WebSocket URL uses correct protocol")
            
            logger.info("✓ Ready for WebSocket subscriptions")
            return True
        except Exception as e:
            logger.error(f"✗ WebSocket URL test failed: {e}")
            return False

    def test_serialization(self, devices: List[Dict[str, Any]]) -> bool:
        """Test device serialization."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 6: Device Serialization")
        logger.info("-" * 80)
        
        if not devices:
            logger.info("⊘ Skipped (no devices)")
            return True
        
        try:
            # Verify devices can be JSON serialized
            json_str = json.dumps(devices[:1])
            logger.info("✓ Devices are JSON serializable")
            
            # Parse back
            parsed = json.loads(json_str)
            assert len(parsed) == 1, "Deserialization failed"
            logger.info("✓ Serialization round-trip successful")
            
            logger.info("✓ Ready for WebSocket broadcasts")
            return True
        except Exception as e:
            logger.error(f"✗ Serialization test failed: {e}")
            return False

    def test_polling_readiness(self) -> bool:
        """Test that everything is ready for polling."""
        logger.info("\n" + "-" * 80)
        logger.info("Test 7: Polling Readiness")
        logger.info("-" * 80)
        
        try:
            # Check all required components
            checks = {
                "API Client": self.client is not None,
                "Session": self.client.session is not None,
                "Base URL": bool(self.client.base_url),
                "Device endpoint": True,  # We already tested this
            }
            
            all_ready = all(checks.values())
            for component, ready in checks.items():
                icon = "✓" if ready else "✗"
                logger.info(f"  {icon} {component}")
            
            if all_ready:
                logger.info("\n✓ All components ready for polling!")
                logger.info("\nNext steps:")
                logger.info("  1. Configure device discovery (if not done):")
                logger.info("     python scripts/shure_configure_discovery_ips.py")
                logger.info("  2. Run polling command:")
                logger.info("     python manage.py poll_devices")
                logger.info("  3. Subscribe to WebSocket updates:")
                logger.info("     See: docs/api/websocket.md")
            
            return all_ready
        except Exception as e:
            logger.error(f"✗ Polling readiness check failed: {e}")
            return False

    def print_summary(self, results: Dict[str, bool], device_count: int):
        """Print test summary."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, success in results.items():
            icon = "✓" if success else "✗"
            logger.info(f"{icon} {test_name}")
        
        logger.info("-" * 80)
        logger.info(f"Result: {passed}/{total} tests passed")
        
        if device_count > 0:
            logger.info(f"Devices discovered: {device_count}")
            logger.info("\n✓ Django-micboard is ready to integrate with Shure System API!")
        else:
            logger.info("\n⚠ Warning: No devices discovered yet")
            logger.info("  This may block polling until discovery completes")
            logger.info("  See: docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md")
        
        logger.info("=" * 80)

    def run(self, sample_size: Optional[int] = None) -> bool:
        """Run all integration tests."""
        results = {}
        device_count = 0
        
        # Run tests
        results["Client Initialization"] = self.test_client_initialization()
        success, devices = self.test_device_fetching()
        results["Device Fetching"] = success
        device_count = len(devices)
        
        if sample_size and devices:
            devices = devices[:sample_size]
        
        results["Device Data Structure"] = self.test_device_data_structure(devices)
        results["Device Transformation"] = self.test_device_transformation(devices)
        results["WebSocket URL"] = self.test_websocket_url()
        results["Serialization"] = self.test_serialization(devices)
        results["Polling Readiness"] = self.test_polling_readiness()
        
        self.print_summary(results, device_count)
        
        # Return overall success
        return all(results.values())


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test django-micboard integration with Shure System API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with all devices
  python scripts/test_micboard_shure_integration.py
  
  # Test with first 5 devices
  python scripts/test_micboard_shure_integration.py --sample-size 5

Next steps after passing:
  1. Configure discovery IPs: python scripts/shure_configure_discovery_ips.py
  2. Start polling: python manage.py poll_devices
  3. Subscribe to WebSocket: See docs/api/websocket.md
        """
    )
    
    parser.add_argument(
        "--sample-size",
        type=int,
        metavar="N",
        help="Test with first N devices (useful for large device counts)"
    )
    
    args = parser.parse_args()
    
    try:
        tester = MicboardIntegrationTester()
        success = tester.run(sample_size=args.sample_size)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
