"""Device network probing service for discovering devices via IP scanning.

Provides low-level HTTP probing to check device reachability and API endpoint
availability. This is separate from the higher-level DiscoveryService which
handles manufacturer-specific discovery orchestration.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class DeviceProbeService:
    """Low-level network probing service for device discovery.

    Probes IP addresses to check for device API endpoint availability.
    Used for initial device discovery before manufacturer-specific sync.
    """

    def __init__(self, *, timeout: int = 5, verify_ssl: bool = False):
        """Initialize device probe service.

        Args:
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.discovered_devices: list[dict[str, Any]] = []
        # Use shared resilient session and a simple in-process circuit breaker
        from micboard.integrations.base_http_client import CircuitBreaker, create_resilient_session

        self.session = create_resilient_session(max_retries=3, backoff_factor=0.5)
        # Circuit named for metrics/observability
        self._circuit = CircuitBreaker(
            name="device_probe", failure_threshold=3, recovery_timeout=30
        )

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry strategy."""
        from micboard.integrations.base_http_client import create_resilient_session

        return create_resilient_session(max_retries=3, backoff_factor=0.5)

    def probe_device(self, ip: str) -> dict[str, Any] | None:
        """Probe a single IP address for device API availability.

        Tries multiple common endpoint patterns:
        - http://{ip}/api/v1/devices
        - https://{ip}/api/v1/devices
        - http://{ip}:80/api/v1/devices
        - https://{ip}:443/api/v1/devices

        Args:
            ip: IP address to probe

        Returns:
            Device info dict if reachable, None otherwise
        """
        endpoints = [
            f"http://{ip}/api/v1/devices",
            f"https://{ip}/api/v1/devices",
            f"http://{ip}:80/api/v1/devices",
            f"https://{ip}:443/api/v1/devices",
        ]

        # Fast-fail if circuit is open to avoid hammering unreachable hosts
        if getattr(self, "_circuit", None) and not self._circuit.allow_request():
            logger.warning("Skipping probe for %s: circuit open", ip)
            return None

        for endpoint in endpoints:
            try:
                response = self.session.get(
                    endpoint,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                    allow_redirects=False,
                )
                if response.status_code in [200, 401]:
                    # Successful probe — reset circuit successes
                    if getattr(self, "_circuit", None):
                        self._circuit.record_success()
                    return {
                        "ip": ip,
                        "endpoint": endpoint,
                        "accessible": response.status_code == 200,
                        "needs_auth": response.status_code == 401,
                    }
            except requests.exceptions.RequestException as e:
                logger.debug("Failed to probe %s: %s", endpoint, e)
                # Record failure in circuit breaker
                if getattr(self, "_circuit", None):
                    self._circuit.record_failure()
                continue

        return None

    def probe_ips(self, ips: Sequence[str]) -> list[dict[str, Any]]:
        """Probe multiple IP addresses.

        Args:
            ips: List of IP addresses to probe

        Returns:
            List of discovered device info dicts
        """
        self.discovered_devices = []
        for ip in ips:
            device_info = self.probe_device(ip.strip())
            if device_info:
                self.discovered_devices.append(device_info)
                logger.info(f"Discovered device at {ip}")
            else:
                logger.debug(f"No device found at {ip}")

        return self.discovered_devices

    def probe_from_file(self, filename: str) -> list[dict[str, Any]]:
        """Probe IP addresses from a file (one per line).

        Args:
            filename: Path to file containing IP addresses

        Returns:
            List of discovered device info dicts
        """
        if not os.path.exists(filename):
            logger.warning(f"IP list file not found: {filename}")
            return []

        ips = []
        with open(filename) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ips.append(line)

        logger.info(f"Loaded {len(ips)} IP addresses from {filename}")
        return self.probe_ips(ips)

    def probe_from_env(self, *, env_var: str = "DEVICE_IPS") -> list[dict[str, Any]]:
        """Probe IP addresses from environment variable.

        Args:
            env_var: Environment variable name (default: DEVICE_IPS)

        Returns:
            List of discovered device info dicts
        """
        ips_str = os.environ.get(env_var, "")
        if not ips_str:
            logger.warning(f"Environment variable {env_var} not set or empty")
            return []

        ips = [ip.strip() for ip in ips_str.split(",") if ip.strip()]
        logger.info(f"Loaded {len(ips)} IP addresses from ${env_var}")
        return self.probe_ips(ips)

    def save_discovery_manifest(
        self,
        filename: str = "device_manifest.json",
        *,
        include_metadata: bool = True,
    ) -> None:
        """Save discovered devices to JSON manifest file.

        Args:
            filename: Output file path
            include_metadata: Include timestamp and count metadata
        """
        if include_metadata:
            manifest = {
                "devices": self.discovered_devices,
                "timestamp": datetime.now().isoformat(),
                "total_count": len(self.discovered_devices),
            }
        else:
            manifest = {"devices": self.discovered_devices}

        with open(filename, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Saved {len(self.discovered_devices)} discovered devices to {filename}")

    def get_discovered_devices(self) -> list[dict[str, Any]]:
        """Get list of all discovered devices from last probe.

        Returns:
            List of device info dicts
        """
        return self.discovered_devices

    def clear_discovered_devices(self) -> None:
        """Clear the list of discovered devices."""
        self.discovered_devices = []


class DeviceAPIHealthChecker:
    """Check health of device API endpoints.

    Used for verifying local or remote API server availability before
    population or sync operations.
    """

    def __init__(self, api_base_url: str = "http://localhost:8000"):
        """Initialize API health checker.

        Args:
            api_base_url: Base URL of API to check
        """
        self.api_base_url = api_base_url.rstrip("/")
        self.session = requests.Session()

    def check_health(self, *, timeout: int = 5) -> bool:
        """Check if API is healthy and responding.

        Args:
            timeout: Request timeout in seconds

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.api_base_url}/api/health",
                timeout=timeout,
            )
            is_healthy = response.status_code == 200
            if is_healthy:
                logger.info(f"API at {self.api_base_url} is healthy")
            else:
                logger.warning(f"API at {self.api_base_url} returned {response.status_code}")
            return is_healthy
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to check API health at {self.api_base_url}: {e}")
            return False

    def get_api_status(self, *, timeout: int = 5) -> dict[str, Any]:
        """Get detailed API status information.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Dictionary with status information
        """
        try:
            response = self.session.get(
                f"{self.api_base_url}/api/health",
                timeout=timeout,
            )
            return {
                "healthy": response.status_code == 200,
                "status_code": response.status_code,
                "api_url": self.api_base_url,
                "reachable": True,
            }
        except requests.exceptions.RequestException as e:
            return {
                "healthy": False,
                "status_code": None,
                "api_url": self.api_base_url,
                "reachable": False,
                "error": str(e),
            }


# Convenience function for quick probing
def probe_device_ip(
    ip: str, *, timeout: int = 5, verify_ssl: bool = False
) -> dict[str, Any] | None:
    """Convenience function to probe a single device IP.

    Args:
        ip: IP address to probe
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Device info dict if reachable, None otherwise
    """
    service = DeviceProbeService(timeout=timeout, verify_ssl=verify_ssl)
    return service.probe_device(ip)
