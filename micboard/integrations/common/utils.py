"""Common utility functions for manufacturer integrations.

Provides shared helper functions for IP validation, data transformation,
and other common operations used across multiple manufacturer implementations.
"""

from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)


def validate_ipv4_list(ips: list[str], log_prefix: str = "") -> list[str]:
    """Validate a list of IP strings, returning only valid IPv4 addresses.

    Args:
        ips: List of IP address strings to validate
        log_prefix: Optional prefix for log messages (e.g., "Shure", "Sennheiser")

    Returns:
        List of valid IPv4 address strings

    Example:
        >>> validate_ipv4_list(["192.168.1.1", "10.0.0.1", "invalid", "::1"])
        ['192.168.1.1', '10.0.0.1']

    Note:
        - Filters out IPv6 addresses
        - Logs warnings for invalid addresses
        - Returns empty list if all inputs are invalid
    """
    valid_ips: list[str] = []
    for ip in ips:
        try:
            addr = ipaddress.ip_address(ip)
            if addr.version == 4:
                valid_ips.append(ip)
            else:
                if log_prefix:
                    logger.warning("%s: Ignoring non-IPv4 address: %s", log_prefix, ip)
                else:
                    logger.warning("Ignoring non-IPv4 address: %s", ip)
        except ValueError:
            if log_prefix:
                logger.warning("%s: Ignoring invalid IP: %s", log_prefix, ip)
            else:
                logger.warning("Ignoring invalid IP: %s", ip)
    return valid_ips


def validate_ipv4_address(ip: str) -> bool:
    """Check if a string is a valid IPv4 address.

    Args:
        ip: IP address string to validate

    Returns:
        True if valid IPv4 address, False otherwise

    Example:
        >>> validate_ipv4_address("192.168.1.1")
        True
        >>> validate_ipv4_address("invalid")
        False
        >>> validate_ipv4_address("::1")
        False
    """
    try:
        addr = ipaddress.ip_address(ip)
        return addr.version == 4
    except ValueError:
        return False


def validate_hostname(hostname: str) -> bool:
    """Check if a string is a valid hostname.

    Args:
        hostname: Hostname string to validate

    Returns:
        True if valid hostname format, False otherwise

    Note:
        - Allows alphanumeric characters, hyphens, and dots
        - Maximum length 253 characters
        - Each label maximum 63 characters
        - Labels cannot start or end with hyphens

    Example:
        >>> validate_hostname("device.example.com")
        True
        >>> validate_hostname("192.168.1.1")
        True
        >>> validate_hostname("-invalid.com")
        False
    """
    if not hostname or len(hostname) > 253:
        return False

    # Allow IP addresses as hostnames
    if validate_ipv4_address(hostname):
        return True

    # Validate hostname labels
    labels = hostname.split(".")
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not all(c.isalnum() or c == "-" for c in label):
            return False

    return True
