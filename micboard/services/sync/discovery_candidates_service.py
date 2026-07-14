"""Discovery candidate computation service."""

from __future__ import annotations

import ipaddress
import logging

from django.core.cache import cache
from django.utils import timezone

from micboard.discovery.network_utils import resolve_fqdns
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.sync.discovery_utils import get_manufacturer_plugin_instance

logger = logging.getLogger(__name__)


class DiscoveryCandidateService:
    """Computes discovery candidates with optional progress tracking."""

    def get_discovery_candidates(
        self,
        manufacturer_code: str,
        *,
        scan_cidrs: bool = False,
        scan_fqdns: bool = False,
        max_hosts: int = 1024,
    ) -> list[str]:
        """Return a deduplicated list of candidate IPs for discovery for the manufacturer.

        This implementation delegates to smaller helpers to keep complexity low and
        reuses existing scanning helpers when possible.
        """
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            return []

        candidates = self._collect_base_candidates(manufacturer)

        try:
            cidr_hosts_map, fqdns_map, _ = self._prepare_scanning_data(
                manufacturer, scan_cidrs, scan_fqdns, max_hosts
            )
            for hosts in cidr_hosts_map.values():
                candidates.extend(hosts)
            for hosts in fqdns_map.values():
                candidates.extend(hosts)
        except Exception:
            logger.exception("Error preparing scanning data for discovery candidates")

        return self._dedupe_preserve_order(candidates)

    def compute_discovery_candidates_with_progress(
        self,
        manufacturer_code: str,
        status_key: str,
        *,
        scan_cidrs: bool = False,
        scan_fqdns: bool = False,
        max_hosts: int = 1024,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> list[str]:
        """Compute discovery candidates while updating a cache-based status key.

        Status dict includes: status, phase, items_total, items_processed, started_at,
        current_cidr/current_fqdn, finished_at/error.
        """
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            cache.set(
                status_key,
                {"status": "error", "error": "manufacturer not found"},
                timeout=3600,
            )
            return []

        candidates = self._collect_base_candidates(manufacturer)

        cidr_hosts_map, fqdns_map, total_to_scan = self._prepare_scanning_data(
            manufacturer, scan_cidrs, scan_fqdns, max_hosts
        )

        self._init_progress_tracking(
            status_key,
            total_to_scan,
            organization_id=organization_id,
            campus_id=campus_id,
        )

        processed = self._perform_scanning_with_progress(
            status_key,
            candidates,
            cidr_hosts_map,
            fqdns_map,
            total_to_scan,
            organization_id=organization_id,
            campus_id=campus_id,
        )

        return self._finalize_candidates(
            status_key,
            candidates,
            total_to_scan,
            processed,
            organization_id=organization_id,
            campus_id=campus_id,
        )

    def _collect_base_candidates(self, manufacturer: Manufacturer) -> list[str]:
        """Collect base candidates from remote discovery IPs and local chassis."""
        candidates = []

        plugin = get_manufacturer_plugin_instance(manufacturer)
        try:
            remote_ips = plugin.get_discovery_ips() or []
            candidates.extend([ip for ip in remote_ips if isinstance(ip, str)])
        except Exception:
            logger.debug("Could not fetch remote discovery IPs for %s", manufacturer.code)

        try:
            for ch in WirelessChassis.objects.filter(manufacturer=manufacturer):
                if ch.ip:
                    candidates.append(ch.ip)
        except Exception:
            logger.exception("Error fetching local chassis IPs for discovery candidates")

        return candidates

    def _prepare_scanning_data(
        self,
        manufacturer: Manufacturer,
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
    ) -> tuple[dict[str, list[str]], dict[str, list[str]], int]:
        """Prepare CIDR and FQDN scanning data."""
        total_to_scan = 0
        cidr_hosts_map = {}
        fqdns_map = {}

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

        if scan_fqdns:
            fqdns = [df.fqdn for df in DiscoveryFQDN.objects.filter(manufacturer=manufacturer)]
            try:
                resolved, _ = resolve_fqdns(fqdns)
                for f, ips in resolved.items():
                    ips_filtered = [ip for ip in ips if isinstance(ip, str)]
                    fqdns_map[f] = ips_filtered
                    total_to_scan += len(ips_filtered)
            except Exception:
                fqdns_map = {f: [] for f in fqdns}

        return cidr_hosts_map, fqdns_map, total_to_scan

    def _init_progress_tracking(
        self,
        status_key: str,
        total_to_scan: int,
        *,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Initialize progress tracking in cache and broadcast initial status."""
        status_data = {
            "status": "running",
            "phase": "scanning",
            "items_total": total_to_scan,
            "items_processed": 0,
            "started_at": str(timezone.now()),
        }
        cache.set(status_key, status_data, timeout=3600)

        BroadcastService.broadcast_progress_update(
            status=status_data,
            organization_id=organization_id,
            campus_id=campus_id,
        )

    def _perform_scanning_with_progress(
        self,
        status_key: str,
        candidates: list[str],
        cidr_hosts_map: dict[str, list[str]],
        fqdns_map: dict[str, list[str]],
        total_to_scan: int,
        *,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> int:
        """Perform CIDR and FQDN scanning while updating progress."""
        processed = 0

        for cidr, hosts in cidr_hosts_map.items():
            self._update_progress(
                status_key, "scanning", total_to_scan, processed, current_cidr=cidr
            )
            processed = self._scan_hosts(
                hosts,
                candidates,
                processed,
                total_to_scan,
                status_key,
                cidr=cidr,
                organization_id=organization_id,
                campus_id=campus_id,
            )

        for f, ips in fqdns_map.items():
            self._update_progress(status_key, "resolving", total_to_scan, processed, current_fqdn=f)
            processed = self._scan_hosts(
                ips,
                candidates,
                processed,
                total_to_scan,
                status_key,
                fqdn=f,
                organization_id=organization_id,
                campus_id=campus_id,
            )

        return processed

    def _scan_hosts(
        self,
        hosts: list[str],
        candidates: list[str],
        processed: int,
        total_to_scan: int,
        status_key: str,
        *,
        cidr: str | None = None,
        fqdn: str | None = None,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> int:
        """Scan a list of hosts, adding to candidates and updating progress."""
        for ip in hosts:
            if str(ip) not in candidates:
                candidates.append(str(ip))
            processed += 1
            if processed % 50 == 0:
                self._update_progress(
                    status_key,
                    "scanning" if cidr else "resolving",
                    total_to_scan,
                    processed,
                    current_cidr=cidr,
                    current_fqdn=fqdn,
                )
                self._broadcast_progress(
                    status_key,
                    organization_id=organization_id,
                    campus_id=campus_id,
                )
        return processed

    def _update_progress(
        self,
        status_key: str,
        phase: str,
        total: int,
        processed: int,
        current_cidr: str | None = None,
        current_fqdn: str | None = None,
    ) -> None:
        """Update progress status in cache."""
        status_data = {
            "status": "running",
            "phase": phase,
            "items_total": total,
            "items_processed": processed,
            "started_at": str(timezone.now()),
        }
        if current_cidr:
            status_data["current_cidr"] = current_cidr
        if current_fqdn:
            status_data["current_fqdn"] = current_fqdn
        cache.set(status_key, status_data, timeout=3600)

    def _broadcast_progress(
        self,
        status_key: str,
        *,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Broadcast progress update via Channels."""
        BroadcastService.broadcast_progress_update(
            status=cache.get(status_key),
            organization_id=organization_id,
            campus_id=campus_id,
        )

    def _finalize_candidates(
        self,
        status_key: str,
        candidates: list[str],
        total_to_scan: int,
        processed: int,
        *,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> list[str]:
        """Finalize candidates by deduplicating and updating final status."""
        deduped = self._dedupe_preserve_order(candidates)

        final_status = {
            "status": "done",
            "count": len(deduped),
            "items_total": total_to_scan,
            "items_processed": processed,
            "finished_at": str(timezone.now()),
        }
        cache.set(status_key, final_status, timeout=3600)

        BroadcastService.broadcast_progress_update(
            status=final_status,
            organization_id=organization_id,
            campus_id=campus_id,
        )

        return deduped

    @staticmethod
    def _dedupe_preserve_order(items: list[str]) -> list[str]:
        """Deduplicate items while preserving insertion order."""
        seen = set()
        deduped: list[str] = []
        for it in items:
            if it not in seen:
                seen.add(it)
                deduped.append(it)
        return deduped
