from __future__ import annotations

import logging
from itertools import islice

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.services.common.base.client import BaseAPIClient
from micboard.services.common.base.rate_limiter import rate_limit
from micboard.services.common.base.utils import validate_ipv4_list
from micboard.utils.exception_logging import sanitized_exception_info

from .exceptions import SennheiserAPIError

logger = logging.getLogger(__name__)


class SennheiserDiscoveryClient:
    """Client for managing Sennheiser SSCv2 API discovery IPs."""

    def __init__(self, api_client: BaseAPIClient) -> None:
        """Initialize discovery sub-client with the parent API client."""
        self.api_client = api_client

    @rate_limit(calls_per_second=1.0)
    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Add IP addresses to the Sennheiser SSCv2 API manual discovery list.

        Placeholder - SSCv2 discovery endpoints need to be verified.
        """
        try:
            bounded_inputs = list(islice(iter(ips), MAX_DISCOVERY_CANDIDATES + 1))
            if len(bounded_inputs) > MAX_DISCOVERY_CANDIDATES:
                logger.warning("Discovery add request exceeded the hard limit")
                return False
            valid_ips = validate_ipv4_list(bounded_inputs, "add_discovery_ips")
            if not valid_ips:
                logger.warning("No valid IPs provided to add_discovery_ips")
                return False
            # Placeholder endpoint
            self.api_client._make_request(
                "PUT", "/api/config/discovery/ips", json={"ips": valid_ips}
            )
            return True
        except SennheiserAPIError as exc:
            logger.error(
                "Failed to add %d discovery IPs",
                len(ips),
                exc_info=sanitized_exception_info(exc),
            )
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
        except SennheiserAPIError as exc:
            logger.error(
                "Failed to fetch discovery IPs",
                exc_info=sanitized_exception_info(exc),
            )
            return []

    @rate_limit(calls_per_second=1.0)
    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Remove IP addresses from the Sennheiser SSCv2 API manual discovery list."""
        try:
            bounded_inputs = list(islice(iter(ips), MAX_DISCOVERY_CANDIDATES + 1))
            if len(bounded_inputs) > MAX_DISCOVERY_CANDIDATES:
                logger.warning("Discovery removal request exceeded the hard limit")
                return False
            valid_ips = validate_ipv4_list(bounded_inputs, "remove_discovery_ips")
            if not valid_ips:
                logger.warning("No valid IPs provided to remove_discovery_ips")
                return False
            # Placeholder endpoint
            self.api_client._make_request(
                "DELETE", "/api/config/discovery/ips", json={"ips": valid_ips}
            )
            return True
        except SennheiserAPIError as exc:
            logger.error(
                "Failed to remove %d discovery IPs",
                len(ips),
                exc_info=sanitized_exception_info(exc),
            )
            return False
