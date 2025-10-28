from __future__ import annotations

import logging

from micboard.manufacturers.base import BaseAPIClient

from .exceptions import SennheiserAPIError
from .rate_limiter import rate_limit
from .utils import validate_ipv4_list

logger = logging.getLogger(__name__)


class SennheiserDiscoveryClient:
    """Client for managing Sennheiser SSCv2 API discovery IPs."""

    def __init__(self, api_client: BaseAPIClient):
        self.api_client = api_client

    @rate_limit(calls_per_second=1.0)
    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Add IP addresses to the Sennheiser SSCv2 API manual discovery list.

        Placeholder - SSCv2 discovery endpoints need to be verified.
        """
        try:
            valid_ips = validate_ipv4_list(ips, "add_discovery_ips")
            if not valid_ips:
                logger.warning("No valid IPs provided to add_discovery_ips")
                return False
            # Placeholder endpoint
            self.api_client._make_request(
                "PUT", "/api/config/discovery/ips", json={"ips": valid_ips}
            )
            return True
        except SennheiserAPIError:
            logger.exception("Failed to add discovery IPs: %s", ips)
            return False

    @rate_limit(calls_per_second=1.0)
    def get_discovery_ips(self) -> list[str]:
        """Retrieve the current manual discovery IPs from Sennheiser SSCv2 API."""
        try:
            res = self.api_client._make_request("GET", "/api/config/discovery/ips")
            if res and isinstance(res, dict):
                ips_from_response = res.get("ips", [])
                if isinstance(ips_from_response, list) and all(
                    isinstance(ip, str) for ip in ips_from_response
                ):
                    return ips_from_response
                else:
                    logger.warning(
                        "Unexpected type for 'ips' in discovery response: %s",
                        type(ips_from_response),
                    )
                    return []
            return []
        except SennheiserAPIError:
            logger.exception("Failed to fetch discovery IPs")
            return []

    @rate_limit(calls_per_second=1.0)
    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Remove IP addresses from the Sennheiser SSCv2 API manual discovery list."""
        try:
            valid_ips = validate_ipv4_list(ips, "remove_discovery_ips")
            if not valid_ips:
                logger.warning("No valid IPs provided to remove_discovery_ips")
                return False
            # Placeholder endpoint
            self.api_client._make_request(
                "DELETE", "/api/config/discovery/ips", json={"ips": valid_ips}
            )
            return True
        except SennheiserAPIError:
            logger.exception("Failed to remove discovery IPs: %s", ips)
            return False