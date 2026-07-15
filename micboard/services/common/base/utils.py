from __future__ import annotations

import ipaddress
import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)


def validate_ipv4_list(ips: Iterable[object], log_prefix: str = "") -> list[str]:
    valid_ips: list[str] = []
    rejected_count = 0
    for ip in ips:
        if not isinstance(ip, str):
            rejected_count += 1
            continue
        try:
            addr = ipaddress.ip_address(ip)
            if addr.version == 4:
                valid_ips.append(str(addr))
            else:
                rejected_count += 1
        except ValueError:
            rejected_count += 1
    if rejected_count:
        logger.warning(
            "%sRejected %d invalid or non-IPv4 addresses",
            f"{log_prefix}: " if log_prefix else "",
            rejected_count,
        )
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
