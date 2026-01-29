import json
import os
from typing import Any, Dict, List, Optional

from django.core.management.base import BaseCommand

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DeviceDiscovery:
    """Discovers and populates Shure devices from VPN sources."""

    def __init__(self, *, timeout: int = 5, verify_ssl: bool = False):
        """Initialize discovery helper with request timeout and SSL verification settings."""
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.discovered_devices: List[Dict[str, Any]] = []
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
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
                if response.status_code in [200, 401]:
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
        self.discovered_devices = []
        for ip in ips:
            device_info = self.probe_device(ip.strip())
            if device_info:
                self.discovered_devices.append(device_info)
        return self.discovered_devices

    def discover_from_file(self, filename: str) -> List[Dict[str, Any]]:
        if not os.path.exists(filename):
            return []
        ips = []
        with open(filename) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ips.append(line)
        return self.discover_from_ips(ips)

    def discover_from_env(self) -> List[Dict[str, Any]]:
        ips_str = os.environ.get("SHURE_DEVICE_IPS", "")
        if not ips_str:
            return []
        ips = [ip.strip() for ip in ips_str.split(",") if ip.strip()]
        return self.discover_from_ips(ips)

    def save_device_manifest(self, filename: str = "device_manifest.json") -> None:
        manifest = {
            "devices": self.discovered_devices,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "total_count": len(self.discovered_devices),
        }
        with open(filename, "w") as f:
            json.dump(manifest, f, indent=2)


class LocalPopulation:
    """Populate local Shure System API with discovered devices."""

    def __init__(self, api_base: str = "http://localhost:8000"):
        """Initialize local population helper with API base and a HTTP session."""
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()

    def check_api_health(self) -> bool:
        try:
            response = self.session.get(f"{self.api_base}/api/health", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def populate_from_manifest(self, manifest_file: str) -> bool:
        if not os.path.exists(manifest_file):
            return False
        with open(manifest_file) as f:
            manifest = json.load(f)
        devices = manifest.get("devices", [])
        for _device in devices:
            pass
            # Placeholder for future enhancement
        return True


class Command(BaseCommand):
    help = "Discover and populate Shure devices from VPN."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="command", help="Command to run")
        discover_parser = subparsers.add_parser("discover", help="Discover devices")
        discover_parser.add_argument("--file", help="File with IP addresses (one per line)")
        discover_parser.add_argument(
            "--env", action="store_true", help="Use SHURE_DEVICE_IPS environment variable"
        )
        discover_parser.add_argument("--ips", help="Comma-separated IP addresses")
        discover_parser.add_argument(
            "--save", default="device_manifest.json", help="Save manifest to file"
        )
        populate_parser = subparsers.add_parser("populate", help="Populate local API")
        populate_parser.add_argument(
            "--manifest", default="device_manifest.json", help="WirelessChassis manifest file"
        )
        test_parser = subparsers.add_parser("test", help="Test device connectivity")
        test_parser.add_argument("--ip", required=True, help="WirelessChassis IP to test")

    def handle(self, *args, **options):
        command = options.get("command")
        if command == "discover":
            discovery = DeviceDiscovery()
            if options.get("file"):
                devices = discovery.discover_from_file(options["file"])
            elif options.get("env"):
                devices = discovery.discover_from_env()
            elif options.get("ips"):
                ips = [ip.strip() for ip in options["ips"].split(",")]
                devices = discovery.discover_from_ips(ips)
            else:
                self.stdout.write(
                    self.style.WARNING("No IPs specified. Use --file, --env, or --ips.")
                )
                return
            if devices:
                discovery.save_device_manifest(options["save"])
        elif command == "populate":
            population = LocalPopulation()
            if population.check_api_health():
                population.populate_from_manifest(options["manifest"])
        elif command == "test":
            discovery = DeviceDiscovery()
            device = discovery.probe_device(options["ip"])
            if device:
                self.stdout.write(json.dumps(device, indent=2))
            else:
                self.stderr.write(self.style.ERROR(f"Could not reach device at {options['ip']}"))
        else:
            self.stdout.write(self.style.WARNING("No command specified. Use --help for options."))
