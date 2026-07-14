"""Shared discovery utilities for common discovery operations.

This module contains utility functions that are shared across discovery services
to reduce duplication and improve maintainability.
"""

import logging

from micboard.discovery.network_utils import resolve_fqdns
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.common.base.plugin import ManufacturerPlugin, get_manufacturer_plugin

logger = logging.getLogger(__name__)


def get_manufacturer_plugin_instance(manufacturer: Manufacturer) -> ManufacturerPlugin:
    """Build the discovery-capable plugin for a manufacturer.

    Args:
        manufacturer: The manufacturer to build a plugin for

    Returns:
        Configured manufacturer plugin
    """
    plugin_class = get_manufacturer_plugin(manufacturer.code)
    plugin = plugin_class(manufacturer)
    return plugin


def is_ip_managed_by_another_manufacturer(
    ip_address: str,
    current_manufacturer: Manufacturer,
    *,
    using: str = "default",
) -> bool:
    """Check if an IP address is already managed by another manufacturer.

    Args:
        ip_address: The IP address to check
        current_manufacturer: The manufacturer making the request

    Returns:
        bool: True if IP is managed by another manufacturer, False otherwise
    """
    return (
        WirelessChassis.objects.using(using)
        .filter(ip=ip_address)
        .exclude(manufacturer=current_manufacturer)
        .exists()
    )


def collect_local_candidates(manufacturer: Manufacturer) -> list[str]:
    """Collect desired discovery candidates from locally managed chassis.

    Args:
        manufacturer: The manufacturer to collect candidates for

    Returns:
        list[str]: List of candidate IP addresses
    """
    return list(
        WirelessChassis.objects.filter(manufacturer=manufacturer)
        .exclude(ip__isnull=True)
        .values_list("ip", flat=True)
    )


def prepare_scanning_data(
    manufacturer: Manufacturer,
    scan_cidrs: bool,
    scan_fqdns: bool,
    max_hosts: int,
) -> tuple[dict[str, list[str]], dict[str, list[str]], int, bool]:
    """Prepare CIDR and FQDN scanning data.

    Args:
        manufacturer: The manufacturer to prepare data for
        scan_cidrs: Whether to scan CIDR ranges
        scan_fqdns: Whether to scan FQDNs
        max_hosts: Maximum hosts to scan per CIDR

    Returns:
        tuple: (cidr_hosts_map, fqdns_map, total_to_scan, sources_complete)
    """
    import ipaddress

    total_to_scan = 0
    cidr_hosts_map = {}
    fqdns_map = {}
    sources_complete = True

    if scan_cidrs:
        cidrs = [dc.cidr for dc in DiscoveryCIDR.objects.filter(manufacturer=manufacturer)]
        for cidr in cidrs:
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                hosts = [str(h) for h in net.hosts()]
                if max_hosts is not None and max_hosts > 0:
                    hosts = hosts[:max_hosts]
                cidr_hosts_map[cidr] = hosts
                total_to_scan += len(hosts)
            except Exception:
                cidr_hosts_map[cidr] = []
                sources_complete = False

    if scan_fqdns:
        fqdns = [df.fqdn for df in DiscoveryFQDN.objects.filter(manufacturer=manufacturer)]
        try:
            resolved, fqdns_complete = resolve_fqdns(fqdns)
            sources_complete = sources_complete and fqdns_complete
            for f, ips in resolved.items():
                ips_filtered = [ip for ip in ips if isinstance(ip, str)]
                fqdns_map[f] = ips_filtered
                total_to_scan += len(ips_filtered)
        except Exception:
            fqdns_map = {f: [] for f in fqdns}
            sources_complete = False

    return cidr_hosts_map, fqdns_map, total_to_scan, sources_complete


def dedupe_preserve_order(items: list[str]) -> list[str]:
    """Deduplicate items while preserving insertion order.

    Args:
        items: List of strings to deduplicate

    Returns:
        list[str]: Deduplicated list preserving original order
    """
    seen = set()
    deduped: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            deduped.append(it)
    return deduped
