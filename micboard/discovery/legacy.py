"""Utilities for network discovery: CIDR expansion and FQDN resolution."""

from __future__ import annotations

# no concurrency imports required for non-probing utilities
import ipaddress
import socket
from collections.abc import Iterator


def expand_cidrs(cidrs: list[str], max_hosts: int = 1024) -> Iterator[str]:
    """Yield IPv4 addresses from CIDR ranges, up to max_hosts per range.

    Args:
        cidrs: list of CIDR strings
        max_hosts: maximum addresses to yield per CIDR (avoid huge scans)
    """
    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except Exception:
            continue
        # Skip very large networks unless explicitly allowed
        hosts = list(net.hosts())
        count = 0
        for ip in hosts:
            yield str(ip)
            count += 1
            if count >= max_hosts:
                break


def resolve_fqdns(fqdns: list[str]) -> dict:
    """Resolve FQDNs to IP addresses.

    Args:
        fqdns: list of hostname strings

    Returns:
        dict mapping fqdn to list of IP addresses
    """
    result = {}
    for fqdn in fqdns:
        try:
            infos = socket.getaddrinfo(fqdn, None)
            ips = list({info[4][0] for info in infos})
            result[fqdn] = ips
        except Exception:
            result[fqdn] = []
    return result


# Note: Direct probing of mic receiver ports is intentionally omitted.
# The Shure System API performs device discovery and probing; this module
# supplies local helpers to expand CIDR ranges and resolve FQDNs only.
