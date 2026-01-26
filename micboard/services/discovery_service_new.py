"""Network discovery service to manage manufacturer IP/FQDN scans."""

import ipaddress
import logging
from typing import Optional, Union, cast

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.utils import timezone

try:
    from channels.layers import get_channel_layer
except ImportError:
    # Channels not installed, provide a no-op function
    def get_channel_layer():
        return None


from micboard.discovery.legacy import expand_cidrs, resolve_fqdns
from micboard.manufacturers import get_manufacturer_plugin
from micboard.manufacturers.base import BaseAPIClient
from micboard.models import DiscoveryCIDR, DiscoveryFQDN, Manufacturer, WirelessChassis

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Manages network discovery across all configured manufacturers."""

    def __init__(self):
        """Initialize discovery helpers and state."""
        pass

    def _get_manufacturer_client(self, manufacturer: Manufacturer) -> BaseAPIClient:
        """Helper to get the API client for a given manufacturer."""
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)
        return plugin.get_client()

    def _is_ip_managed_by_another_manufacturer(
        self, ip_address: str, current_manufacturer: Manufacturer
    ) -> bool:
        """Check if an IP address is already managed by another manufacturer."""
        # Check if any WirelessChassis object already exists with this IP and
        # a different manufacturer
        return cast(
            bool,
            WirelessChassis.objects.filter(ip=ip_address)
            .exclude(manufacturer=current_manufacturer)
            .exists(),
        )

    def add_discovery_candidate(
        self,
        ip_address: str,
        manufacturer: Manufacturer,
        source: str = "manual",
    ) -> bool:
        """Adds an IP address to a manufacturer's discovery list, enforcing exclusivity."""
        if self._is_ip_managed_by_another_manufacturer(ip_address, manufacturer):
            logger.warning(
                "IP %s is already managed by another manufacturer. Skipping for %s.",
                ip_address,
                manufacturer.code,
            )
        client = self._get_manufacturer_client(manufacturer)
        try:
            success = client.add_discovery_ips([ip_address])
            if success:
                logger.info(
                    "Successfully added IP %s to %s discovery list (source: %s).",
                    ip_address,
                    manufacturer.code,
                    source,
                )
            else:
                logger.warning(
                    "Failed to add IP %s to %s discovery list (source: %s).",
                    ip_address,
                    manufacturer.code,
                    source,
                )
            return success
        except Exception as e:
            logger.error(
                "Error adding IP %s to %s discovery list (source: %s): %s",
                ip_address,
                manufacturer.code,
                source,
                e,
            )
            return False

    def remove_discovery_candidate(
        self,
        ip_address: str,
        manufacturer: Manufacturer,
    ) -> bool:
        """Removes an IP address from a manufacturer's discovery list."""
        client = self._get_manufacturer_client(manufacturer)
        try:
            success = client.remove_discovery_ips([ip_address])
            if success:
                logger.info(
                    "Successfully removed IP %s from %s discovery list.",
                    ip_address,
                    manufacturer.code,
                )
            else:
                logger.warning(
                    "Failed to remove IP %s from %s discovery list.", ip_address, manufacturer.code
                )
            return success
        except Exception as e:
            logger.error(
                "Error removing IP %s from %s discovery list: %s", ip_address, manufacturer.code, e
            )
            return False

    def run_global_discovery(
        self, scan_cidrs: bool = True, scan_fqdns: bool = True, max_hosts: int = 1024
    ):
        """Runs discovery across all configured manufacturers."""
        manufacturers = Manufacturer.objects.all()
        for manufacturer in manufacturers:
            logger.info("Starting discovery for manufacturer: %s", manufacturer.name)
            self._run_manufacturer_discovery(manufacturer, scan_cidrs, scan_fqdns, max_hosts)

    def _run_manufacturer_discovery(
        self,
        manufacturer: Manufacturer,
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
    ):
        """Runs discovery for a single manufacturer."""
        # Collect IPs from various sources
        candidate_ips: list[str] = []

        # 1. IPs from existing chassis for this manufacturer
        for ch in WirelessChassis.objects.filter(manufacturer=manufacturer):
            if ch.ip:
                candidate_ips.append(ch.ip)

        # 2. IPs from DiscoveryCIDR
        if scan_cidrs:
            cidrs = [dc.cidr for dc in DiscoveryCIDR.objects.filter(manufacturer=manufacturer)]
            for ip in expand_cidrs(cidrs, max_hosts=max_hosts):
                candidate_ips.append(ip)

        # 3. IPs from DiscoveryFQDN
        if scan_fqdns:
            fqdns = [df.fqdn for df in DiscoveryFQDN.objects.filter(manufacturer=manufacturer)]
            resolved_fqdns = resolve_fqdns(fqdns)
            for _, ips in resolved_fqdns.items():
                candidate_ips.extend(ips)

        # Deduplicate and add to manufacturer's discovery list
        unique_candidate_ips = list(dict.fromkeys(candidate_ips))
        logger.info(
            "Manufacturer %s: Found %d unique candidate IPs from local sources.",
            manufacturer.code,
            len(unique_candidate_ips),
        )

        client = self._get_manufacturer_client(manufacturer)
        existing_discovery_ips = []
        try:
            existing_discovery_ips = client.get_discovery_ips()
        except Exception as e:
            logger.warning(
                "Could not retrieve existing discovery IPs for %s: %s", manufacturer.code, e
            )

        ips_to_add = [ip for ip in unique_candidate_ips if ip not in existing_discovery_ips]
        ips_to_remove = [ip for ip in existing_discovery_ips if ip not in unique_candidate_ips]

        if ips_to_add:
            logger.info("Adding %d IPs to %s discovery list.", len(ips_to_add), manufacturer.code)
            for ip in ips_to_add:
                self.add_discovery_candidate(ip, manufacturer, source="global_scan")

        if ips_to_remove:
            logger.info(
                "Removing %d IPs from %s discovery list.", len(ips_to_remove), manufacturer.code
            )
            for ip in ips_to_remove:
                self.remove_discovery_candidate(ip, manufacturer)

        logger.info("Finished discovery for manufacturer: %s", manufacturer.name)

    def get_all_managed_ips(self) -> set[str]:
        """Returns a set of all IP addresses currently managed by any manufacturer."""
        managed_ips = set()
        for ch in WirelessChassis.objects.all():
            if ch.ip:
                managed_ips.add(ch.ip)
        return managed_ips

    def get_manufacturer_for_ip(self, ip_address: str) -> Union[Manufacturer, None]:
        """Returns the manufacturer managing a given IP address, if any."""
        try:
            chassis = WirelessChassis.objects.filter(ip=ip_address).first()
            if chassis:
                return chassis.manufacturer
        except Exception as e:
            logger.error("Error getting manufacturer for IP %s: %s", ip_address, e)
        return None

    def get_device_detail(
        self,
        *,
        manufacturer_code: str | None = None,
        device_id: str | None = None,
    ) -> dict[str, dict]:
        """Fetch device detail via manufacturer plugins without using signals.

        Args:
            manufacturer_code: Optional code to scope the lookup. If omitted,
                              all manufacturers are queried.
            device_id: Device identifier from the manufacturer's API.

        Returns:
            Mapping of manufacturer code -> {status, device|error}
        """
        if not device_id:
            return {}

        if manufacturer_code:
            manufacturers = Manufacturer.objects.filter(code=manufacturer_code)
        else:
            manufacturers = Manufacturer.objects.all()

        results: dict[str, dict] = {}

        for mfr in manufacturers:
            try:
                plugin_cls = get_manufacturer_plugin(mfr.code)
                plugin = plugin_cls(mfr)

                dev = plugin.get_device(device_id)
                if not dev:
                    continue

                try:
                    channels = plugin.get_device_channels(device_id)
                    dev["channels"] = channels
                except Exception:
                    logger.debug("No channel data for %s", device_id)

                transformed = plugin.transform_device_data(dev)
                if not transformed:
                    results[mfr.code] = {"status": "error", "error": "transform failed"}
                    continue

                results[mfr.code] = {"status": "success", "device": transformed}

                # If scoped to a specific manufacturer, short-circuit on first success
                if manufacturer_code:
                    return results

            except Exception as exc:
                logger.exception("Error fetching device %s for %s: %s", device_id, mfr.code, exc)
                results[mfr.code] = {"status": "error", "error": str(exc)}

        return results

    def get_discovery_candidates(
        self,
        manufacturer_code: str,
        *,
        scan_cidrs: bool = False,
        scan_fqdns: bool = False,
        max_hosts: int = 1024,
    ) -> list[str]:
        """Return a deduplicated list of candidate IPs for discovery for the manufacturer.

        This aggregates the client's manual discovery IPs (if available), local chassis
        IP addresses that are not yet in the discovery list, and optionally expanded
        CIDRs and resolved FQDNs from DiscoveryCIDR and DiscoveryFQDN models.
        """
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            return []

        candidate_ips: list[str] = []

        client = self._get_manufacturer_client(manufacturer)
        if client and hasattr(client, "get_discovery_ips"):
            try:
                remote_ips = client.get_discovery_ips() or []
                candidate_ips.extend([ip for ip in remote_ips if isinstance(ip, str)])
            except Exception:
                # Ignore remote fetch errors; continue with other sources
                logger.debug("Could not fetch remote discovery IPs for %s", manufacturer.code)

        # 2) Include local chassis IPs that might not be discovered yet
        try:
            for ch in WirelessChassis.objects.filter(manufacturer=manufacturer):
                if ch.ip:
                    candidate_ips.append(ch.ip)
        except Exception:
            logger.exception("Error fetching local chassis IPs for discovery candidates")

        # 3) Optionally expand CIDRs and resolve FQDNs from DiscoveryCIDR and DiscoveryFQDN models
        try:
            cidrs = [dc.cidr for dc in DiscoveryCIDR.objects.filter(manufacturer=manufacturer)]
            fqdns = [df.fqdn for df in DiscoveryFQDN.objects.filter(manufacturer=manufacturer)]

            if scan_cidrs and cidrs:
                for cidr in cidrs:
                    for ip in expand_cidrs([cidr], max_hosts=max_hosts):
                        candidate_ips.append(ip)

            if scan_fqdns and fqdns:
                resolved = resolve_fqdns(fqdns)
                for _f, ips in resolved.items():
                    for ip in ips:
                        candidate_ips.append(ip)
        except Exception:
            logger.exception("Error expanding CIDRs or resolving FQDNs for discovery candidates")

        # Deduplicate while preserving order
        seen = set()
        deduped: list[str] = []
        for ip in candidate_ips:
            if ip not in seen:
                seen.add(ip)
                deduped.append(ip)

        return deduped

    def compute_discovery_candidates_with_progress(
        self,
        manufacturer_code: str,
        status_key: str,
        *,
        scan_cidrs: bool = False,
        scan_fqdns: bool = False,
        max_hosts: int = 1024,
    ) -> list[str]:
        """Compute discovery candidates while updating a cache-based status key.

        Status dict includes: status, phase, items_total, items_processed, started_at,
        current_cidr/current_fqdn, finished_at/error.
        """
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            cache.set(
                status_key, {"status": "error", "error": "manufacturer not found"}, timeout=3600
            )
            return []

        candidates = self._collect_base_candidates(manufacturer)

        # Prepare scanning data
        cidr_hosts_map, fqdns_map, total_to_scan = self._prepare_scanning_data(
            manufacturer, scan_cidrs, scan_fqdns, max_hosts
        )

        # Initialize progress tracking
        self._init_progress_tracking(status_key, total_to_scan)

        # Perform scanning with progress updates
        processed = self._perform_scanning_with_progress(
            status_key, candidates, cidr_hosts_map, fqdns_map, total_to_scan
        )

        # Finalize and return deduplicated candidates
        return self._finalize_candidates(status_key, candidates, total_to_scan, processed)

    def _collect_base_candidates(self, manufacturer: Manufacturer) -> list[str]:
        """Collect base candidates from remote discovery IPs and local chassis."""
        candidates = []

        # Remote discovery IPs
        client = self._get_manufacturer_client(manufacturer)
        if client and hasattr(client, "get_discovery_ips"):
            try:
                remote_ips = client.get_discovery_ips() or []
                candidates.extend([ip for ip in remote_ips if isinstance(ip, str)])
            except Exception:
                logger.debug("Could not fetch remote discovery IPs for %s", manufacturer.code)

        # Local chassis IPs
        try:
            for ch in WirelessChassis.objects.filter(manufacturer=manufacturer):
                if ch.ip:
                    candidates.append(ch.ip)
        except Exception:
            logger.exception("Error fetching local chassis IPs for discovery candidates")

        return candidates

    def _prepare_scanning_data(
        self, manufacturer: Manufacturer, scan_cidrs: bool, scan_fqdns: bool, max_hosts: int
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
                resolved = resolve_fqdns(fqdns)
                for f, ips in resolved.items():
                    ips_filtered = [ip for ip in ips if isinstance(ip, str)]
                    fqdns_map[f] = ips_filtered
                    total_to_scan += len(ips_filtered)
            except Exception:
                fqdns_map = {f: [] for f in fqdns}

        return cidr_hosts_map, fqdns_map, total_to_scan

    def _init_progress_tracking(self, status_key: str, total_to_scan: int) -> None:
        """Initialize progress tracking in cache and broadcast initial status."""
        status_data = {
            "status": "running",
            "phase": "scanning",
            "items_total": total_to_scan,
            "items_processed": 0,
            "started_at": str(timezone.now()),
        }
        cache.set(status_key, status_data, timeout=3600)

        # Broadcast initial progress
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "progress_update", "status": status_data},
                )
        except Exception:
            logger.debug("Channels layer not available for progress updates")

    def _perform_scanning_with_progress(
        self,
        status_key: str,
        candidates: list[str],
        cidr_hosts_map: dict[str, list[str]],
        fqdns_map: dict[str, list[str]],
        total_to_scan: int,
    ) -> int:
        """Perform CIDR and FQDN scanning while updating progress."""
        processed = 0
        channel_layer = get_channel_layer()

        # Scan CIDRs
        for cidr, hosts in cidr_hosts_map.items():
            self._update_progress(
                status_key, "scanning", total_to_scan, processed, current_cidr=cidr
            )
            processed = self._scan_hosts(
                hosts, candidates, processed, total_to_scan, status_key, channel_layer, cidr=cidr
            )

        # Resolve FQDNs
        for f, ips in fqdns_map.items():
            self._update_progress(status_key, "resolving", total_to_scan, processed, current_fqdn=f)
            processed = self._scan_hosts(
                ips, candidates, processed, total_to_scan, status_key, channel_layer, fqdn=f
            )

        return processed

    def _scan_hosts(
        self,
        hosts: list[str],
        candidates: list[str],
        processed: int,
        total_to_scan: int,
        status_key: str,
        channel_layer,
        *,
        cidr: Optional[str] = None,
        fqdn: Optional[str] = None,
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
                self._broadcast_progress(status_key, channel_layer)
        return processed

    def _update_progress(
        self,
        status_key: str,
        phase: str,
        total: int,
        processed: int,
        current_cidr: Optional[str] = None,
        current_fqdn: Optional[str] = None,
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

    def _broadcast_progress(self, status_key: str, channel_layer) -> None:
        """Broadcast progress update via Channels."""
        try:
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "progress_update", "status": cache.get(status_key)},
                )
        except Exception:
            logger.debug("Failed to send progress update")

    def _finalize_candidates(
        self, status_key: str, candidates: list[str], total_to_scan: int, processed: int
    ) -> list[str]:
        """Finalize candidates by deduplicating and updating final status."""
        # Deduplicate
        seen = set()
        deduped = []
        for ip in candidates:
            if ip not in seen:
                seen.add(ip)
                deduped.append(ip)

        # Update final status
        final_status = {
            "status": "done",
            "count": len(deduped),
            "items_total": total_to_scan,
            "items_processed": processed,
            "finished_at": str(timezone.now()),
        }
        cache.set(status_key, final_status, timeout=3600)

        # Broadcast final status
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "progress_update", "status": final_status},
                )
        except Exception:
            logger.debug("Failed to send final progress update")

        return deduped
