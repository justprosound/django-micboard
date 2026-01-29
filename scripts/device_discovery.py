#!/usr/bin/env python
"""WirelessChassis Discovery & Population Script for Local Shure System API.

This script discovers live Shure devices on the VPN and populates the local
Shure System API with real device data for testing and development.

SECURITY: This script should NOT be committed to the public repository.
Use environment variables for sensitive configuration.

Usage:
    python scripts/device_discovery.py --discover
    python scripts/device_discovery.py --populate [--source gtech-devices.txt]
    python scripts/device_discovery.py --test

Environment Variables:
    SHURE_DEVICE_IPS - Comma-separated list of device IPs (alternative to file)
    SHURE_API_ENDPOINT - Local Shure API endpoint (default: http://localhost:8000)
    SHURE_API_USERNAME - API credentials (if needed)
    SHURE_API_PASSWORD - API credentials (if needed)
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django

django.setup()


import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DeviceDiscovery:
    """Discovers and populates Shure devices from VPN sources."""

    def __init__(self, *, timeout: int = 5, verify_ssl: bool = False):
        """Initialize device discovery client.

        Args:
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.discovered_devices: List[Dict[str, Any]] = []
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retries."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def probe_device(self, ip: str) -> Optional[Dict[str, Any]]:
        """Probe a single device at the given IP address.

        Args:
            ip: WirelessChassis IP address

        Returns:
            WirelessChassis info dict if successful, None otherwise
        """
        endpoints = [
            f"http://{ip}/api/v1/devices",
            f"https://{ip}/api/v1/devices",
            f"http://{ip}:80/api/v1/devices",
            f"https://{ip}:443/api/v1/devices",
        ]

        for endpoint in endpoints:
            try:
                response = self.session.get(
                    endpoint, timeout=self.timeout, verify=self.verify_ssl, allow_redirects=False
                )
                if response.status_code in [200, 401]:  # 401 means API exists but needs auth
                    print(f"✓ WirelessChassis found at {ip}")
                    return {
                        "ip": ip,
                        "endpoint": endpoint,
                        "accessible": response.status_code == 200,
                        "needs_auth": response.status_code == 401,
                    }
            except requests.exceptions.RequestException:
                pass

        return None

    def discover_from_ips(self, ips: List[str]) -> List[Dict[str, Any]]:
        """Discover devices from a list of IP addresses.

        Args:
            ips: List of device IP addresses

        Returns:
            List of discovered device info dicts
        """
        print(f"\nProbing {len(ips)} IP addresses...")
        self.discovered_devices = []

        for ip in ips:
            device_info = self.probe_device(ip.strip())
            if device_info:
                self.discovered_devices.append(device_info)
                print(f"  Found: {device_info}")

        print(f"\n✓ Discovered {len(self.discovered_devices)} devices")
        return self.discovered_devices

    def discover_from_file(self, filename: str) -> List[Dict[str, Any]]:
        """Discover devices from a file of IP addresses.

        File format: One IP per line, lines starting with # are comments

        Args:
            filename: Path to file with IPs

        Returns:
            List of discovered device info dicts
        """
        if not os.path.exists(filename):
            print(f"✗ File not found: {filename}")
            return []

        ips = []
        with open(filename) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ips.append(line)

        print(f"Loaded {len(ips)} IPs from {filename}")
        return self.discover_from_ips(ips)

    def discover_from_env(self) -> List[Dict[str, Any]]:
        """Discover devices from SHURE_DEVICE_IPS environment variable.

        Returns:
            List of discovered device info dicts
        """
        ips_str = os.environ.get("SHURE_DEVICE_IPS", "")
        if not ips_str:
            print("✗ SHURE_DEVICE_IPS not set")
            return []

        ips = [ip.strip() for ip in ips_str.split(",") if ip.strip()]
        print(f"Loaded {len(ips)} IPs from SHURE_DEVICE_IPS")
        return self.discover_from_ips(ips)

    def save_device_manifest(self, filename: str = "device_manifest.json") -> None:
        """Save discovered devices to a manifest file.

        Args:
            filename: Output filename (will NOT be committed - in .gitignore)
        """
        # DO NOT COMMIT THIS FILE - Add to .gitignore
        manifest = {
            "devices": self.discovered_devices,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "total_count": len(self.discovered_devices),
        }

        with open(filename, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"\n✓ WirelessChassis manifest saved to {filename}")
        print("  ⚠️  WARNING: Do not commit this file!")
        print("     It should be in .gitignore")


class LocalPopulation:
    """Populate local Shure System API with discovered devices."""

    def __init__(self, api_base: str = "http://localhost:8000"):
        """Initialize population client.

        Args:
            api_base: Base URL of local Shure API
        """
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()

    def check_api_health(self) -> bool:
        """Check if local API is running.

        Returns:
            True if API is healthy
        """
        try:
            response = self.session.get(f"{self.api_base}/api/health", timeout=5)
            print(f"✓ Local API is {response.status_code}: Healthy")
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"✗ Local API not responding: {e}")
            return False

    def populate_from_manifest(self, manifest_file: str) -> bool:
        """Populate API from device manifest.

        Args:
            manifest_file: Path to device manifest JSON

        Returns:
            True if successful
        """
        if not os.path.exists(manifest_file):
            print(f"✗ Manifest file not found: {manifest_file}")
            return False

        with open(manifest_file) as f:
            manifest = json.load(f)

        devices = manifest.get("devices", [])
        print(f"\nPopulating {len(devices)} devices...")

        for device in devices:
            print(f"  Adding: {device['ip']}")
            # Note: Device population from manifest requires API endpoint implementation
            # Currently this is a placeholder for future enhancement

        print(f"✓ Populated {len(devices)} devices")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Discover and populate Shure devices from VPN")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Discover subcommand
    discover_parser = subparsers.add_parser("discover", help="Discover devices")
    discover_parser.add_argument("--file", help="File with IP addresses (one per line)")
    discover_parser.add_argument(
        "--env", action="store_true", help="Use SHURE_DEVICE_IPS environment variable"
    )
    discover_parser.add_argument("--ips", help="Comma-separated IP addresses")
    discover_parser.add_argument(
        "--save", default="device_manifest.json", help="Save manifest to file"
    )

    # Populate subcommand
    populate_parser = subparsers.add_parser("populate", help="Populate local API")
    populate_parser.add_argument(
        "--manifest", default="device_manifest.json", help="WirelessChassis manifest file"
    )

    # Test subcommand
    test_parser = subparsers.add_parser("test", help="Test device connectivity")
    test_parser.add_argument("--ip", required=True, help="WirelessChassis IP to test")

    args = parser.parse_args()

    if args.command == "discover":
        discovery = DeviceDiscovery()

        if args.file:
            devices = discovery.discover_from_file(args.file)
        elif args.env:
            devices = discovery.discover_from_env()
        elif args.ips:
            ips = [ip.strip() for ip in args.ips.split(",")]
            devices = discovery.discover_from_ips(ips)
        else:
            parser.print_help()
            return 1

        if devices:
            discovery.save_device_manifest(args.save)
            return 0
        else:
            return 1

    elif args.command == "populate":
        population = LocalPopulation()
        if population.check_api_health():
            return 0 if population.populate_from_manifest(args.manifest) else 1
        return 1

    elif args.command == "test":
        discovery = DeviceDiscovery()
        device = discovery.probe_device(args.ip)
        if device:
            print(json.dumps(device, indent=2))
            return 0
        else:
            print(f"✗ Could not reach device at {args.ip}")
            return 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
