import ipaddress
import logging
from typing import Union

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.utils import timezone

from micboard.discovery.legacy import expand_cidrs, resolve_fqdns
from micboard.manufacturers import get_manufacturer_plugin
from micboard.manufacturers.base import BaseAPIClient
from micboard.models import DiscoveryCIDR, DiscoveryFQDN, Manufacturer, Receiver

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Manages network discovery across all configured manufacturers."""

    def __init__(self):
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
        # Check if any Receiver object already exists with this IP and a different manufacturer
        return (
            Receiver.objects.filter(ip=ip_address)
            .exclude(manufacturer=current_manufacturer)
            .exists()
        )

    def add_discovery_candidate(
        self,
        ip_address: str,
        manufacturer: Manufacturer,
        source: str = "manual",
    ) -> bool:  # type: ignore
        """Adds an IP address to a manufacturer's discovery list, enforcing exclusivity."""
        if self._is_ip_managed_by_another_manufacturer(ip_address, manufacturer):
            logger.warning(
                "IP %s is already managed by another manufacturer. Skipping for %s.",
                ip_address,
                manufacturer.code,
        client = cast(BaseAPIClient, self._get_manufacturer_client(manufacturer))
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

        # 1. IPs from existing Receivers for this manufacturer
        for rx in Receiver.objects.filter(manufacturer=manufacturer):
            if rx.ip:
                candidate_ips.append(rx.ip)

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
        for rx in Receiver.objects.all():
            if rx.ip:
                managed_ips.add(rx.ip)
        return managed_ips

    def get_manufacturer_for_ip(self, ip_address: str) -> Union[Manufacturer, None]:
        """Returns the manufacturer managing a given IP address, if any."""
        try:
            receiver = Receiver.objects.filter(ip=ip_address).first()
            if receiver:
                return Manufacturer(receiver.manufacturer)
        except Exception as e:
            logger.error("Error getting manufacturer for IP %s: %s", ip_address, e)
        return None

    def get_discovery_candidates(
        self,
        manufacturer_code: str,
        *,
        scan_cidrs: bool = False,
        scan_fqdns: bool = False,
        max_hosts: int = 1024,
    ) -> list[str]:
        """Return a deduplicated list of candidate IPs for discovery for the manufacturer.

        This aggregates the client's manual discovery IPs (if available), local Receiver
        IP addresses that are not yet in the discovery list, and optionally expanded
        CIDRs and resolved FQDNs from MicboardConfig.
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

        # 2) Include local receiver IPs that might not be discovered yet
        try:
            for rx in Receiver.objects.filter(manufacturer=manufacturer):
                if rx.ip:
                    candidate_ips.append(rx.ip)
        except Exception:
            logger.exception("Error fetching local receiver IPs for discovery candidates")

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

        candidates: list[str] = []

        # remote ips
        try:
            client = self._get_manufacturer_client(manufacturer)
            remote_ips = []
            if client and hasattr(client, "get_discovery_ips"):
                try:
                    remote_ips = client.get_discovery_ips() or []
                except Exception:
                    remote_ips = []
            candidates.extend([ip for ip in remote_ips if isinstance(ip, str)])
        except Exception:
            cache.set(
                status_key, {"status": "error", "error": "failed fetching remote ips"}, timeout=3600
            )
            return []

        # local receivers
        try:
            for rx in Receiver.objects.filter(manufacturer=manufacturer):
                if rx.ip:
                    candidates.append(rx.ip)
        except Exception:
            cache.set(
                status_key, {"status": "error", "error": "failed fetching receivers"}, timeout=3600
            )
            return []

        # prepare scanning maps
        total_to_scan = 0
        cidr_hosts_map: dict[str, list[str]] = {}
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

        fqdns_map: dict[str, list[str]] = {}
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

        cache.set(
            status_key,
            {
                "status": "running",
                "phase": "scanning",
                "items_total": total_to_scan,
                "items_processed": 0,
                "started_at": str(timezone.now()),
            },
            timeout=3600,
        )
        # Broadcast initial progress via Channels
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "progress_update", "status": cache.get(status_key)},
                )
        except Exception:
            logger.debug("Channels layer not available for progress updates")

        processed = 0
        try:
            for cidr, hosts in cidr_hosts_map.items():
                cache.set(
                    status_key,
                    {
                        "status": "running",
                        "phase": "scanning",
                        "items_total": total_to_scan,
                        "items_processed": processed,
                        "current_cidr": cidr,
                        "started_at": str(timezone.now()),
                    },
                    timeout=3600,
                )
                for ip in hosts:
                    if str(ip) not in candidates:
                        candidates.append(str(ip))
                    processed += 1
                    if processed % 50 == 0:
                        cache.set(
                            status_key,
                            {
                                "status": "running",
                                "phase": "scanning",
                                "items_total": total_to_scan,
                                "items_processed": processed,
                                "current_cidr": cidr,
                                "started_at": str(timezone.now()),
                            },
                            timeout=3600,
                        )
                        try:
                            if channel_layer:
                                async_to_sync(channel_layer.group_send)(
                                    "micboard_updates",
                                    {"type": "progress_update", "status": cache.get(status_key)},
                                )
                        except Exception:
                            logger.debug("Failed to send progress update for %s", cidr)

            for f, ips in fqdns_map.items():
                cache.set(
                    status_key,
                    {
                        "status": "running",
                        "phase": "resolving",
                        "items_total": total_to_scan,
                        "items_processed": processed,
                        "current_fqdn": f,
                        "started_at": str(timezone.now()),
                    },
                    timeout=3600,
                )
                for ip in ips:
                    if str(ip) not in candidates:
                        candidates.append(str(ip))
                    processed += 1
                    if processed % 50 == 0:
                        cache.set(
                            status_key,
                            {
                                "status": "running",
                                "phase": "resolving",
                                "items_total": total_to_scan,
                                "items_processed": processed,
                                "current_fqdn": f,
                                "started_at": str(timezone.now()),
                            },
                            timeout=3600,
                        )
                        try:
                            if channel_layer:
                                async_to_sync(channel_layer.group_send)(
                                    "micboard_updates",
                                    {"type": "progress_update", "status": cache.get(status_key)},
                                )
                        except Exception:
                            logger.debug("Failed to send progress update for fqdn %s", f)

        except Exception as exc:
            cache.set(status_key, {"status": "error", "error": str(exc)}, timeout=3600)
            return []

        seen = set()
        deduped: list[str] = []
        for ip in candidates:
            if ip not in seen:
                seen.add(ip)
                deduped.append(ip)

        cache.set(
            status_key,
            {
                "status": "done",
                "count": len(deduped),
                "items_total": total_to_scan,
                "items_processed": processed,
                "finished_at": str(timezone.now()),
            },
            timeout=3600,
        )
        try:
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "progress_update", "status": cache.get(status_key)},
                )
        except Exception:
            logger.debug("Failed to send final progress update")
        return deduped
