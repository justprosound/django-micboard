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

    def __init__(self, api_client: BaseAPIClient) -> None:
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
            # A failed or unreadable GET must abort: the PUT replaces the whole list.
            existing = validate_ipv4_list(self._read_discovery_ips(), "existing_discovery_ips")

            combined = list(dict.fromkeys(list(existing) + list(valid_ips)))
            if len(combined) > MAX_DISCOVERY_CANDIDATES:
                logger.warning("Merged discovery list exceeded the hard limit")
                return False
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

    def _read_discovery_ips(self) -> list[str]:
        """Return the remote list; raise ShureAPIError if it cannot be read as one."""
        res = self.api_client._make_request("GET", "/api/v1/config/discovery/ips")
        ips = res.get("ips") if isinstance(res, dict) else None
        if (
            not isinstance(ips, list)
            or len(ips) > MAX_DISCOVERY_CANDIDATES
            or not all(isinstance(ip, str) for ip in ips)
        ):
            raise ShureAPIError("Discovery list response was unreadable")
        return ips

    @rate_limit(calls_per_second=1.0)
    def get_discovery_ips(self) -> list[str]:
        """Retrieve the current manual discovery IPs from Shure System API.

        Raises ShureAPIError when the list cannot be read, so callers never
        mistake a failed read for an empty list.
        """
        return self._read_discovery_ips()

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
