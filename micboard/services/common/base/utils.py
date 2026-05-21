from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)


def validate_ipv4_list(ips: list[str], log_prefix: str = "") -> list[str]:
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
    try:
        addr = ipaddress.ip_address(ip)
        return addr.version == 4
    except ValueError:
        return False


def validate_hostname(hostname: str) -> bool:
    if not hostname or len(hostname) > 253:
        return False

    if validate_ipv4_address(hostname):
        return True

    labels = hostname.split(".")
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not all(c.isalnum() or c == "-" for c in label):
            return False

    return True
