"""Collect bounded candidate sources for full discovery synchronization."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from django.db.models import Subquery

from micboard.discovery.limits import (
    DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
    clamp_candidate_limit,
)
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice, DiscoveryCIDR, DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.discovery_dtos import (
    DiscoveryCandidatePage,
    DiscoveryScanSourcePage,
)
from micboard.services.sync.discovery_source_cursor_service import (
    DiscoverySource,
    DiscoverySourceCursorService,
)
from micboard.services.sync.discovery_utils import expand_scanning_sources


class DiscoveryCandidateSourceService:
    """Own bounded source selection and expansion for a full discovery sync."""

    @staticmethod
    def configured_scan_sources(
        manufacturer: Manufacturer,
        *,
        scan_cidrs: bool,
        scan_fqdns: bool,
        limit: int,
    ) -> DiscoveryScanSourcePage:
        """Load a bounded set of enabled scan sources for a manufacturer."""
        source_limit = clamp_candidate_limit(limit)
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
            group="full-sync-scan-sources",
            sources=sources,
            limit=source_limit,
        )
        source_order: list[Literal["cidrs", "fqdns"]] = []
        for source_name in pages:
            if source_name == "cidrs":
                source_order.append("cidrs")
            elif source_name == "fqdns":
                source_order.append("fqdns")
        return DiscoveryScanSourcePage(
            cidrs=pages["cidrs"].values if "cidrs" in pages else [],
            fqdns=pages["fqdns"].values if "fqdns" in pages else [],
            source_order=source_order,
            sources_complete=all(page.sources_complete for page in pages.values()),
        )

    @staticmethod
    def collect_inventory_candidates(
        manufacturer: Manufacturer,
        *,
        limit: int = DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
    ) -> DiscoveryCandidatePage:
        """Collect a bounded, stable inventory projection for one manufacturer."""
        candidate_limit = clamp_candidate_limit(limit)
        configured_queryset = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
        ).exclude(ip__isnull=True)
        configured_ips = configured_queryset.values("ip")
        sources = [
            DiscoverySource(
                name="configured",
                queryset=configured_queryset,
                value_field="ip",
            ),
            DiscoverySource(
                name="staged",
                queryset=(
                    DiscoveredDevice.objects.filter(manufacturer=manufacturer).exclude(
                        ip__in=Subquery(configured_ips)
                    )
                ),
                value_field="ip",
            ),
        ]
        pages = DiscoverySourceCursorService.rotating_pages(
            manufacturer,
            group="full-sync-local-inventory",
            sources=sources,
            limit=candidate_limit,
        )
        return DiscoveryCandidatePage(
            candidates=[
                *pages["configured"].values,
                *pages["staged"].values,
            ],
            sources_complete=all(page.sources_complete for page in pages.values()),
        )

    @staticmethod
    def collect_scanned_candidates(
        *,
        cidrs: list[str],
        fqdns: list[str],
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
        source_order: Sequence[str] | None = None,
    ) -> DiscoveryCandidatePage:
        """Expand enabled scan sources into a deduplicated candidate list."""
        candidate_limit = clamp_candidate_limit(max_hosts)
        cidr_hosts, fqdn_hosts, _total, sources_complete = expand_scanning_sources(
            cidrs if scan_cidrs else [],
            fqdns if scan_fqdns else [],
            max_hosts=candidate_limit,
            source_order=source_order or ["cidrs", "fqdns"],
        )
        ordered_maps = {
            "cidrs": cidr_hosts,
            "fqdns": fqdn_hosts,
        }
        effective_order = [
            source_name
            for source_name in dict.fromkeys(source_order or ["cidrs", "fqdns"])
            if source_name in ordered_maps
        ]
        candidate_ips = [
            address
            for source_name in effective_order
            for addresses in ordered_maps[source_name].values()
            for address in addresses
        ]
        return DiscoveryCandidatePage(
            candidates=list(dict.fromkeys(candidate_ips))[:candidate_limit],
            sources_complete=sources_complete,
        )
