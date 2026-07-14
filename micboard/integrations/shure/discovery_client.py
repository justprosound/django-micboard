from __future__ import annotations

import logging
from itertools import islice

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.services.common.base.client import BaseAPIClient
from micboard.services.common.base.rate_limiter import rate_limit
from micboard.services.common.base.utils import validate_ipv4_list
from micboard.utils.exception_logging import sanitized_exception_info

from .exceptions import ShureAPIError

logger = logging.getLogger(__name__)


class ShureDiscoveryClient:
    """Client for managing Shure System API discovery IPs."""

    def __init__(self, api_client: BaseAPIClient):
        """Initialize discovery client with parent API client."""
        self.api_client = api_client

    @rate_limit(calls_per_second=1.0)  # Discovery operations are less frequent
    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Add IP addresses to the Shure System API manual discovery list.

        Args:
            ips: List of IPv4 address strings

        Returns:
            True if the request was accepted (202), False otherwise
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
            # Retrieve existing discovery IPs
            existing = []
            try:
                # Shure API uses /api/v1/ base path in this deployment
                res = self.api_client._make_request("GET", "/api/v1/config/discovery/ips")
                if res and isinstance(res, dict):
                    remote_ips = res.get("ips", [])
                    if (
                        not isinstance(remote_ips, list)
                        or len(remote_ips) > MAX_DISCOVERY_CANDIDATES
                    ):
                        logger.warning("Existing discovery response was invalid or oversized")
                        return False
                    existing = validate_ipv4_list(remote_ips, "existing_discovery_ips")
            except ShureAPIError:
                logger.debug("No existing discovery IPs returned; starting fresh")

            combined = list(dict.fromkeys(list(existing) + list(valid_ips)))
            # Replace discovery list via PUT
            self.api_client._make_request(
                "PUT", "/api/v1/config/discovery/ips", json={"ips": combined}
            )
            return True
        except ShureAPIError as exc:
            logger.error(
                "Failed to add %d discovery IPs",
                len(ips),
                exc_info=sanitized_exception_info(exc),
            )
            return False

    @rate_limit(calls_per_second=1.0)
    def get_discovery_ips(self) -> list[str]:
        """Retrieve the current manual discovery IPs from Shure System API.

        Returns a list of IP address strings.
        """
        try:
            res = self.api_client._make_request("GET", "/api/v1/config/discovery/ips")
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
        except ShureAPIError as exc:
            logger.error(
                "Failed to fetch discovery IPs",
                exc_info=sanitized_exception_info(exc),
            )
            return []

    @rate_limit(calls_per_second=1.0)
    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Remove IP addresses from the Shure System API manual discovery list.

        Uses the /api/v1/config/discovery/ips/remove endpoint which accepts a
        JSON body of {"ips": [..]} and returns success if accepted.
        Returns True on success, False otherwise.
        """
        try:
            bounded_inputs = list(islice(iter(ips), MAX_DISCOVERY_CANDIDATES + 1))
            if len(bounded_inputs) > MAX_DISCOVERY_CANDIDATES:
                logger.warning("Discovery removal request exceeded the hard limit")
                return False
            valid_ips = validate_ipv4_list(bounded_inputs, "remove_discovery_ips")
            if not valid_ips:
                logger.warning("No valid IPs provided to remove_discovery_ips")
                return False
            # Use the dedicated remove endpoint if available.
            # Some Shure API deployments accept PATCH/POST to /remove.
            try:
                self.api_client._make_request(
                    "PATCH", "/api/v1/config/discovery/ips/remove", json={"ips": valid_ips}
                )
            except ShureAPIError:
                # Fallback to POST if PATCH not supported
                self.api_client._make_request(
                    "POST", "/api/v1/config/discovery/ips/remove", json={"ips": valid_ips}
                )
            return True
        except ShureAPIError as exc:
            logger.error(
                "Failed to remove %d discovery IPs",
                len(ips),
                exc_info=sanitized_exception_info(exc),
            )
            return False
