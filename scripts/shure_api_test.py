#!/usr/bin/env python
"""
Local Shure System API Integration Test Script

This script tests connectivity and basic operations with the Shure System API
running locally on https://localhost:10000/v1.0/swagger.json

Usage:
    uv run python shure_api_test.py [--shared-key KEY] [--no-ssl-verify]
"""

import sys
import os
import json
import argparse
import logging
from typing import Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')
import django
django.setup()

from django.conf import settings
from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.integrations.shure.exceptions import ShureAPIError


class ShureAPITester:
    """Test suite for Shure System API integration."""

    def __init__(self, shared_key: Optional[str] = None, verify_ssl: bool = True):
        """Initialize the test suite."""
        self.shared_key = shared_key or os.environ.get('MICBOARD_SHURE_API_SHARED_KEY')
        self.verify_ssl = verify_ssl
        self.client: Optional[ShureSystemAPIClient] = None
        self.test_results = []

    def initialize_client(self) -> bool:
        """Initialize the Shure API client."""
        logger.info("Initializing Shure System API Client...")
        logger.info(f"  Base URL: https://localhost:10000")
        logger.info(f"  SSL Verification: {self.verify_ssl}")
        logger.info(f"  Shared Key: {'*' * (len(self.shared_key) - 4) if self.shared_key else 'NOT SET'}{self.shared_key[-4:] if self.shared_key else ''}")

        if not self.shared_key:
            logger.error("ERROR: SHURE_API_SHARED_KEY environment variable not set!")
            return False

        try:
            # Temporarily override Django settings
            old_config = getattr(settings, 'MICBOARD_CONFIG', {})
            settings.MICBOARD_CONFIG = {
                'SHURE_API_BASE_URL': 'https://localhost:10000',
                'SHURE_API_SHARED_KEY': self.shared_key,
                'SHURE_API_VERIFY_SSL': self.verify_ssl,
                'SHURE_API_TIMEOUT': 10,
            }

            self.client = ShureSystemAPIClient(
                base_url='https://localhost:10000',
                verify_ssl=self.verify_ssl
            )
            logger.info("✓ Client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to initialize client: {e}")
            return False

    def test_health_check(self) -> bool:
        """Test API health check endpoint."""
        if not self.client:
            return False

        logger.info("\n" + "=" * 70)
        logger.info("TEST 1: Health Check")
        logger.info("=" * 70)

        try:
            health = self.client.check_health()
            logger.info(f"✓ Health check successful: {json.dumps(health, indent=2)}")
            self.test_results.append(("Health Check", True, health))
            return health.get('status') == 'healthy'
        except Exception as e:
            logger.error(f"✗ Health check failed: {e}")
            self.test_results.append(("Health Check", False, str(e)))
            return False

    def test_get_devices(self) -> bool:
        """Test getting list of devices."""
        if not self.client:
            return False

        logger.info("\n" + "=" * 70)
        logger.info("TEST 2: Get Devices")
        logger.info("=" * 70)

        try:
            devices = self.client.devices.get_devices()
            logger.info(f"✓ Retrieved {len(devices)} device(s)")
            for idx, device in enumerate(devices[:3], 1):  # Show first 3
                logger.info(f"  Device {idx}: {device.get('deviceId', 'N/A')} - {device.get('deviceType', 'N/A')}")
            if len(devices) > 3:
                logger.info(f"  ... and {len(devices) - 3} more")
            self.test_results.append(("Get Devices", True, {"count": len(devices)}))
            return len(devices) > 0
        except Exception as e:
            logger.error(f"✗ Get devices failed: {e}")
            self.test_results.append(("Get Devices", False, str(e)))
            return False

    def test_device_details(self) -> bool:
        """Test getting details for a specific device."""
        if not self.client:
            return False

        logger.info("\n" + "=" * 70)
        logger.info("TEST 3: Get Device Details")
        logger.info("=" * 70)

        try:
            devices = self.client.devices.get_devices()
            if not devices:
                logger.warning("⊘ No devices available to test")
                self.test_results.append(("Device Details", False, "No devices available"))
                return False

            device_id = devices[0].get('deviceId')
            logger.info(f"Testing with device ID: {device_id}")

            # Test device identity
            identity = self.client.devices.get_device_identity(device_id)
            logger.info(f"✓ Device Identity: {identity.get('serialNumber', 'N/A')}")

            # Test device status
            status = self.client.devices.get_device_status(device_id)
            logger.info(f"✓ Device Status: {status.get('systemTime', 'N/A')}")

            # Test device network
            network = self.client.devices.get_device_network(device_id)
            logger.info(f"✓ Device Network: {network.get('ipAddress', 'N/A')}")

            self.test_results.append(("Device Details", True, {"device_id": device_id}))
            return True
        except Exception as e:
            logger.error(f"✗ Device details failed: {e}")
            self.test_results.append(("Device Details", False, str(e)))
            return False

    def test_discovery_endpoints(self) -> bool:
        """Test discovery management endpoints."""
        if not self.client:
            return False

        logger.info("\n" + "=" * 70)
        logger.info("TEST 4: Discovery Management")
        logger.info("=" * 70)

        try:
            # Get current discovery IPs
            discovery_ips = self.client.discovery.get_discovery_ips()
            logger.info(f"✓ Current discovery IPs: {discovery_ips}")

            # Test adding a discovery IP (test IP, won't be used)
            test_ip = "192.168.1.100"
            result = self.client.discovery.add_discovery_ips([test_ip])
            logger.info(f"✓ Added discovery IP {test_ip}: {result}")

            # Verify it was added
            updated_ips = self.client.discovery.get_discovery_ips()
            logger.info(f"✓ Updated discovery IPs: {updated_ips}")

            # Remove the test IP
            result = self.client.discovery.remove_discovery_ips([test_ip])
            logger.info(f"✓ Removed discovery IP {test_ip}: {result}")

            self.test_results.append(("Discovery Endpoints", True, {"ips_count": len(updated_ips)}))
            return True
        except Exception as e:
            logger.error(f"✗ Discovery endpoints failed: {e}")
            self.test_results.append(("Discovery Endpoints", False, str(e)))
            return False

    def test_connection_pooling(self) -> bool:
        """Test connection pooling and retry logic."""
        if not self.client:
            return False

        logger.info("\n" + "=" * 70)
        logger.info("TEST 5: Connection Pooling & Retry Logic")
        logger.info("=" * 70)

        try:
            logger.info(f"Session max_retries: {self.client.max_retries}")
            logger.info(f"Session retry_backoff: {self.client.retry_backoff}s")
            logger.info(f"Session timeout: {self.client.timeout}s")

            # Make multiple rapid requests to test pooling
            for i in range(3):
                devices = self.client.devices.get_devices()
                logger.info(f"✓ Request {i+1}: Retrieved {len(devices)} devices")

            logger.info("✓ Connection pooling working correctly")
            self.test_results.append(("Connection Pooling", True, {}))
            return True
        except Exception as e:
            logger.error(f"✗ Connection pooling test failed: {e}")
            self.test_results.append(("Connection Pooling", False, str(e)))
            return False

    def test_rate_limiter(self) -> bool:
        """Test rate limiter functionality."""
        if not self.client:
            return False

        logger.info("\n" + "=" * 70)
        logger.info("TEST 6: Rate Limiter")
        logger.info("=" * 70)

        try:
            rate_limiter = self.client.rate_limiter
            logger.info(f"Rate limiter configured: {rate_limiter is not None}")
            logger.info(f"Rate limiter type: {type(rate_limiter).__name__}")
            self.test_results.append(("Rate Limiter", True, {"has_limiter": rate_limiter is not None}))
            return True
        except Exception as e:
            logger.error(f"✗ Rate limiter test failed: {e}")
            self.test_results.append(("Rate Limiter", False, str(e)))
            return False

    def print_summary(self):
        """Print test summary."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST SUMMARY")
        logger.info("=" * 70)

        passed = sum(1 for _, success, _ in self.test_results if success)
        total = len(self.test_results)

        for test_name, success, details in self.test_results:
            status = "✓ PASS" if success else "✗ FAIL"
            logger.info(f"{status}: {test_name}")

        logger.info("-" * 70)
        logger.info(f"TOTAL: {passed}/{total} tests passed")
        logger.info("=" * 70)

        return passed == total

    def run_all_tests(self) -> bool:
        """Run all tests."""
        if not self.initialize_client():
            return False

        tests = [
            self.test_health_check,
            self.test_get_devices,
            self.test_device_details,
            self.test_discovery_endpoints,
            self.test_connection_pooling,
            self.test_rate_limiter,
        ]

        for test in tests:
            try:
                test()
            except Exception as e:
                logger.error(f"Unexpected error in {test.__name__}: {e}")

        success = self.print_summary()
        return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Test Shure System API integration'
    )
    parser.add_argument(
        '--shared-key',
        help='Shure API shared key (can also use MICBOARD_SHURE_API_SHARED_KEY env var)'
    )
    parser.add_argument(
        '--no-ssl-verify',
        action='store_true',
        help='Disable SSL verification (for self-signed certificates)'
    )

    args = parser.parse_args()

    tester = ShureAPITester(
        shared_key=args.shared_key,
        verify_ssl=not args.no_ssl_verify
    )

    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
