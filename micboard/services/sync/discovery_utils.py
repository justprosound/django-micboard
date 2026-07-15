"""Shared discovery utilities for common discovery operations.

This module contains utility functions that are shared across discovery services
to reduce duplication and improve maintainability.
"""

import ipaddress
import logging
from collections.abc import Iterator, Sequence

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES, clamp_candidate_limit
from micboard.discovery.network_utils import resolve_fqdns
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.common.base.plugin import ManufacturerPlugin, get_manufacturer_plugin
from micboard.services.sync.discovery_source_cursor_service import (
    DiscoverySource,
    DiscoverySourceCursorService,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

AddressIterator = tuple[str, str, Iterator[str]]


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


def collect_local_candidates(
    manufacturer: Manufacturer,
    *,
    limit: int = MAX_DISCOVERY_CANDIDATES,
) -> tuple[list[str], bool]:
    """Collect a bounded desired-state projection from locally managed chassis.

    Args:
        manufacturer: The manufacturer to collect candidates for

    Returns:
        Candidate IPs in stable database order and whether every row was included
    """
    candidate_limit = clamp_candidate_limit(limit)
    source = DiscoverySource(
        name="configured",
        queryset=WirelessChassis.objects.filter(manufacturer=manufacturer).exclude(ip__isnull=True),
        value_field="ip",
    )
    page = DiscoverySourceCursorService.rotating_page(
        manufacturer,
        group="reconciliation-local-inventory",
        source=source,
        limit=candidate_limit,
    )
    return page.values, page.sources_complete


def expand_scanning_sources(
    cidrs: list[str],
    fqdns: list[str],
    *,
    max_hosts: int,
    source_order: Sequence[str] = ("cidrs", "fqdns"),
) -> tuple[dict[str, list[str]], dict[str, list[str]], int, bool]:
    """Interleave configured definitions under one bounded address budget."""
    candidate_limit = clamp_candidate_limit(max_hosts)
    cidr_hosts_map, cidr_iterators, cidrs_complete = _build_cidr_iterators(cidrs)
    fqdns_map, fqdn_iterators, fqdns_complete = _build_fqdn_iterators(fqdns)
    iterators = {"cidrs": cidr_iterators, "fqdns": fqdn_iterators}
    ordered_source_names = [
        source_name
        for source_name in dict.fromkeys([*source_order, "cidrs", "fqdns"])
        if source_name in iterators
    ]
    active = [
        (source_name, key, source_iterator)
        for source_name in ordered_source_names
        for key, source_iterator in iterators[source_name]
    ]
    total_to_scan, iterators_complete = _consume_address_iterators(
        active,
        cidr_hosts_map=cidr_hosts_map,
        fqdns_map=fqdns_map,
        limit=candidate_limit,
    )
    return (
        cidr_hosts_map,
        fqdns_map,
        total_to_scan,
        cidrs_complete and fqdns_complete and iterators_complete,
    )


def _build_cidr_iterators(
    cidrs: list[str],
) -> tuple[dict[str, list[str]], list[tuple[str, Iterator[str]]], bool]:
    """Build lazy host iterators while retaining invalid-definition completeness."""
    hosts_map: dict[str, list[str]] = {cidr: [] for cidr in cidrs}
    iterators: list[tuple[str, Iterator[str]]] = []
    sources_complete = True
    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            sources_complete = False
            continue
        iterators.append((cidr, (str(host) for host in network.hosts())))
    return hosts_map, iterators, sources_complete


def _build_fqdn_iterators(
    fqdns: list[str],
) -> tuple[dict[str, list[str]], list[tuple[str, Iterator[str]]], bool]:
    """Resolve FQDN definitions and retain malformed-result completeness."""
    addresses_map: dict[str, list[str]] = {fqdn: [] for fqdn in fqdns}
    if not fqdns:
        return addresses_map, [], True
    try:
        resolved, sources_complete = resolve_fqdns(fqdns)
    except Exception as exc:
        logger.exception(
            "Unexpected error resolving discovery FQDNs",
            exc_info=sanitized_exception_info(exc),
        )
        return addresses_map, [], False

    iterators: list[tuple[str, Iterator[str]]] = []
    for fqdn in fqdns:
        raw_addresses = resolved.get(fqdn, [])
        valid_addresses = [address for address in raw_addresses if isinstance(address, str)]
        sources_complete = sources_complete and len(valid_addresses) == len(raw_addresses)
        iterators.append((fqdn, iter(valid_addresses)))
    return addresses_map, iterators, sources_complete


def _consume_address_iterators(
    active: list[AddressIterator],
    *,
    cidr_hosts_map: dict[str, list[str]],
    fqdns_map: dict[str, list[str]],
    limit: int,
) -> tuple[int, bool]:
    """Round-robin selected definitions and report whether each iterator ended."""
    total_to_scan = 0
    while active and total_to_scan < limit:
        next_active: list[AddressIterator] = []
        for index, (source_name, key, source_iterator) in enumerate(active):
            try:
                address = next(source_iterator)
            except StopIteration:
                continue
            if source_name == "cidrs":
                cidr_hosts_map[key].append(address)
            else:
                fqdns_map[key].append(address)
            total_to_scan += 1
            next_active.append((source_name, key, source_iterator))
            if total_to_scan == limit:
                next_active.extend(active[index + 1 :])
                break
        active = next_active
    iterators_complete = not active or not any(
        next(source_iterator, None) is not None for _source_name, _key, source_iterator in active
    )
    return total_to_scan, iterators_complete


def prepare_scanning_data(
    manufacturer: Manufacturer,
    scan_cidrs: bool,
    scan_fqdns: bool,
    max_hosts: int,
) -> tuple[dict[str, list[str]], dict[str, list[str]], int, bool]:
    """Prepare CIDR and FQDN scan data under one global bounded address budget."""
    candidate_limit = clamp_candidate_limit(max_hosts)
    sources = [
        *(
            [
                DiscoverySource(
                    name="cidrs",
                    queryset=DiscoveryCIDR.objects.filter(manufacturer=manufacturer),
                    value_field="cidr",
                )
            ]
            if scan_cidrs
            else []
        ),
        *(
            [
                DiscoverySource(
                    name="fqdns",
                    queryset=DiscoveryFQDN.objects.filter(manufacturer=manufacturer),
                    value_field="fqdn",
                )
            ]
            if scan_fqdns
            else []
        ),
    ]
    pages = DiscoverySourceCursorService.rotating_pages(
        manufacturer,
        group="reconciliation-scan-sources",
        sources=sources,
        limit=candidate_limit,
    )
    cidr_hosts_map, fqdns_map, total_to_scan, expansion_complete = expand_scanning_sources(
        pages["cidrs"].values if "cidrs" in pages else [],
        pages["fqdns"].values if "fqdns" in pages else [],
        max_hosts=candidate_limit,
        source_order=list(pages),
    )
    definitions_complete = all(page.sources_complete for page in pages.values())
    return (
        cidr_hosts_map,
        fqdns_map,
        total_to_scan,
        definitions_complete and expansion_complete,
    )


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
