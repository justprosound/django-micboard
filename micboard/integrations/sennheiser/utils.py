from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)


def validate_ipv4_list(ips: list[str], log_prefix: str) -> list[str]:
    """Helper to validate a list of IP strings, returning only valid IPv4 addresses."""
    valid_ips: list[str] = []
    for ip in ips:
        try:
            addr = ipaddress.ip_address(ip)
            if addr.version == 4:
                valid_ips.append(ip)
            else:
                logger.warning("%s: Ignoring non-IPv4 address: %s", log_prefix, ip)
        except ValueError:
            logger.warning("%s: Ignoring invalid IP: %s", log_prefix, ip)
    return valid_ips
