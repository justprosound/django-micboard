"""Utilities for network discovery: CIDR expansion and FQDN resolution."""

from __future__ import annotations

# no concurrency imports required for non-probing utilities
import ipaddress
import socket
from collections.abc import Iterator
from itertools import islice

from micboard.discovery.limits import clamp_candidate_limit


def expand_cidrs(cidrs: list[str], max_hosts: int = 1024) -> Iterator[str]:
    """Yield addresses lazily, up to max_hosts across all supplied ranges.

    Args:
        cidrs: list of CIDR strings
        max_hosts: maximum total addresses to yield (avoid huge scans)
    """
    remaining = clamp_candidate_limit(max_hosts)
    if remaining == 0:
        return
    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            # Invalid CIDR notation - skip silently as this is expected during user input
            continue
        # Iterate lazily so a large user-supplied network cannot exhaust memory.
        for ip in islice(net.hosts(), remaining):
            yield str(ip)
            remaining -= 1
        if remaining == 0:
            return


def resolve_fqdns(fqdns: list[str]) -> tuple[dict[str, list[str]], bool]:
    """Resolve FQDNs to IP addresses and report whether every lookup succeeded.

    Args:
        fqdns: list of hostname strings

    Returns:
        Tuple containing the address mapping and a source-completeness flag.
    """
    result: dict[str, list[str]] = {}
    complete = True
    for fqdn in fqdns:
        try:
            infos = socket.getaddrinfo(fqdn, None)
            ips = sorted({str(info[4][0]) for info in infos})
            result[fqdn] = ips
        except (socket.gaierror, OSError):
            # Preserve the failed key while telling reconciliation not to remove stale addresses.
            result[fqdn] = []
            complete = False
    return result, complete


# Note: Direct probing of mic receiver ports is intentionally omitted.
# The Shure System API performs device discovery and probing; this module
# supplies local helpers to expand CIDR ranges and resolve FQDNs only.
