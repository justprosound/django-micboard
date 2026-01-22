#!/usr/bin/env python3
"""
Standalone Device Discovery for Shure VPN Devices

Discovers live Shure devices on VPN without Django dependencies.
Probes connectivity and generates device manifest.

Usage:
    python scripts/device_discovery_standalone.py test --ip 172.21.1.100
    python scripts/device_discovery_standalone.py discover --ips "172.21.1.100,172.21.1.101"
    python scripts/device_discovery_standalone.py discover --file devices.txt
"""

import sys
import json
import argparse
from typing import List, Dict, Optional, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DeviceDiscovery:
    """Discovers Shure devices from VPN sources."""

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
            total=2,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def probe_device(self, ip: str) -> Optional[Dict[str, Any]]:
        """Probe a single device at the given IP address.
        
        Args:
            ip: Device IP address
            
        Returns:
            Device info dict if successful, None otherwise
        """
        # Common Shure API endpoints
        endpoints = [
            f"http://{ip}/api/v1/devices",
            f"https://{ip}/api/v1/devices",
            f"http://{ip}/api/v1.0/devices",
            f"https://{ip}/api/v1.0/devices",
            f"http://{ip}:80/api/v1/devices",
            f"https://{ip}:443/api/v1/devices",
        ]

        print(f"  Probing {ip}...", end=" ", flush=True)
        
        for endpoint in endpoints:
            try:
                response = self.session.get(
                    endpoint,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                    allow_redirects=False
                )
                # 200 = accessible, 401/403 = API exists but needs auth
                if response.status_code in [200, 401, 403]:
                    print(f"✓ Found at {endpoint.split('//')[1].split('/')[0]}")
                    return {
                        "ip": ip,
                        "endpoint": endpoint,
                        "accessible": response.status_code == 200,
                        "needs_auth": response.status_code in [401, 403],
                        "status_code": response.status_code,
                    }
            except requests.exceptions.ConnectTimeout:
                continue
            except requests.exceptions.ConnectionError:
                continue
            except requests.exceptions.RequestException:
                continue

        print("✗ Not reachable")
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
        import os
        if not os.path.exists(filename):
            print(f"✗ File not found: {filename}")
            return []

        ips = []
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ips.append(line)

        print(f"Loaded {len(ips)} IPs from {filename}")
        return self.discover_from_ips(ips)

    def save_device_manifest(self, filename: str = "device_manifest.json") -> None:
        """Save discovered devices to a manifest file.
        
        Args:
            filename: Output filename (will NOT be committed - in .gitignore)
        """
        from datetime import datetime
        
        manifest = {
            "devices": self.discovered_devices,
            "timestamp": datetime.now().isoformat(),
            "total_count": len(self.discovered_devices),
        }

        with open(filename, 'w') as f:
            json.dump(manifest, f, indent=2)

        print(f"\n✓ Device manifest saved to {filename}")
        print("  ⚠️  WARNING: Do not commit this file!")
        print("     It should be in .gitignore")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Discover Shure devices from VPN'
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Discover subcommand
    discover_parser = subparsers.add_parser('discover', help='Discover devices')
    discover_parser.add_argument(
        '--file',
        help='File with IP addresses (one per line)'
    )
    discover_parser.add_argument(
        '--ips',
        help='Comma-separated IP addresses'
    )
    discover_parser.add_argument(
        '--save',
        default='device_manifest.json',
        help='Save manifest to file'
    )
    discover_parser.add_argument(
        '--timeout',
        type=int,
        default=5,
        help='Timeout in seconds (default: 5)'
    )

    # Test subcommand
    test_parser = subparsers.add_parser('test', help='Test device connectivity')
    test_parser.add_argument(
        '--ip',
        required=True,
        help='Device IP to test'
    )
    test_parser.add_argument(
        '--timeout',
        type=int,
        default=5,
        help='Timeout in seconds (default: 5)'
    )

    args = parser.parse_args()

    if args.command == 'discover':
        discovery = DeviceDiscovery(timeout=args.timeout)

        if args.file:
            devices = discovery.discover_from_file(args.file)
        elif args.ips:
            ips = [ip.strip() for ip in args.ips.split(',')]
            devices = discovery.discover_from_ips(ips)
        else:
            parser.print_help()
            return 1

        if devices:
            discovery.save_device_manifest(args.save)
            return 0
        else:
            return 1

    elif args.command == 'test':
        discovery = DeviceDiscovery(timeout=args.timeout)
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


if __name__ == '__main__':
    sys.exit(main())
