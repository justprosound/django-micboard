"""Network discovery service to manage manufacturer IP/FQDN scans."""

import ipaddress
import logging
from typing import cast

from django.core.cache import cache
from django.utils import timezone

from asgiref.sync import async_to_sync

try:
    from channels.layers import get_channel_layer
except ImportError:
    # Channels not installed, provide a no-op function
    def get_channel_layer():
        return None


from micboard.discovery.network_utils import expand_cidrs, resolve_fqdns
from micboard.manufacturers import get_manufacturer_plugin
from micboard.manufacturers.base import BaseAPIClient
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis

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
                    "Failed to remove IP %s from %s discovery list.",
                    ip_address,
                    manufacturer.code,
                )
            return success
        except Exception as e:
            logger.error(
                "Error removing IP %s from %s discovery list: %s",
                ip_address,
                manufacturer.code,
                e,
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

    @staticmethod
    def trigger_manufacturer_discovery(
        manufacturer_pk: int, scan_cidrs: bool = True, scan_fqdns: bool = True
    ) -> None:
        """Trigger discovery for a specific manufacturer (task or sync).

        Centralizes the scheduling logic previously embedded in model mixins.
        """
        from micboard.utils.dependencies import HAS_DJANGO_Q

        if not manufacturer_pk:
            return

        if HAS_DJANGO_Q:
            try:
                from django_q.tasks import async_task

                from micboard.tasks.sync.discovery import (
                    run_manufacturer_discovery_task,
                )

                async_task(
                    run_manufacturer_discovery_task,
                    manufacturer_pk,
                    scan_cidrs,
                    scan_fqdns,
                )
                return
            except Exception:
                logger.exception(
                    "Failed to enqueue discovery task for manufacturer %s",
                    manufacturer_pk,
                )

        # Fallback: run synchronously
        try:
            ds = DiscoveryService()
            manufacturer = Manufacturer.objects.get(pk=manufacturer_pk)
            ds._run_manufacturer_discovery(manufacturer, scan_cidrs, scan_fqdns, max_hosts=1024)
        except Exception:
            logger.exception(
                "Failed to run discovery synchronously for manufacturer %s",
                manufacturer_pk,
            )

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
        chassis_ips = (
            WirelessChassis.objects.filter(manufacturer=manufacturer)
            .exclude(ip__isnull=True)
            .exclude(ip="")
            .values_list("ip", flat=True)
        )
        candidate_ips.extend(chassis_ips)

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
                "Could not retrieve existing discovery IPs for %s: %s",
                manufacturer.code,
                e,
            )

        ips_to_add = [ip for ip in unique_candidate_ips if ip not in existing_discovery_ips]
        ips_to_remove = [ip for ip in existing_discovery_ips if ip not in unique_candidate_ips]

        if ips_to_add:
            logger.info(
                "Adding %d IPs to %s discovery list.",
                len(ips_to_add),
                manufacturer.code,
            )
            for ip in ips_to_add:
                self.add_discovery_candidate(ip, manufacturer, source="global_scan")

        if ips_to_remove:
            logger.info(
                "Removing %d IPs from %s discovery list.",
                len(ips_to_remove),
                manufacturer.code,
            )
            for ip in ips_to_remove:
                self.remove_discovery_candidate(ip, manufacturer)

        logger.info("Finished discovery for manufacturer: %s", manufacturer.name)

    def get_all_managed_ips(self) -> set[str]:
        """Returns a set of all IP addresses currently managed by any manufacturer."""
        return set(
            WirelessChassis.objects.exclude(ip__isnull=True)
            .exclude(ip="")
            .values_list("ip", flat=True)
        )

    def get_manufacturer_for_ip(self, ip_address: str) -> Manufacturer | None:
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

        This implementation delegates to smaller helpers to keep complexity low and
        reuses existing scanning helpers when possible.
        """
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            return []

        # Start with base candidates (remote + local chassis)
        candidates = self._collect_base_candidates(manufacturer)

        # Optionally add expanded CIDR hosts and resolved FQDNs
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

        # Deduplicate while preserving insertion order
        return self._dedupe_preserve_order(candidates)

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
                status_key,
                {"status": "error", "error": "manufacturer not found"},
                timeout=3600,
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
                hosts,
                candidates,
                processed,
                total_to_scan,
                status_key,
                channel_layer,
                cidr=cidr,
            )

        # Resolve FQDNs
        for f, ips in fqdns_map.items():
            self._update_progress(status_key, "resolving", total_to_scan, processed, current_fqdn=f)
            processed = self._scan_hosts(
                ips,
                candidates,
                processed,
                total_to_scan,
                status_key,
                channel_layer,
                fqdn=f,
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
        cidr: str | None = None,
        fqdn: str | None = None,
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
        deduped = self._dedupe_preserve_order(candidates)

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

    def refresh_discovered_devices_from_api(self, queryset) -> tuple[int, int]:
        """Refresh discovered device records from manufacturer APIs.

        Dispatches work to a per-device refresher helper to keep complexity low.
        Returns (updated_count, failed_count).
        """
        updated = 0
        failed = 0

        for discovered in queryset:
            ok = self._refresh_single_discovered_device(discovered)
            if ok:
                updated += 1
            else:
                failed += 1

        return updated, failed

    def _refresh_single_discovered_device(self, discovered) -> bool:
        """Refresh a single DiscoveredDevice record from its manufacturer's API.

        Returns True on success, False on failure.
        """
        try:
            manufacturer = discovered.manufacturer
            if not manufacturer:
                logger.warning(
                    "DiscoveredDevice %s has no manufacturer; skipping",
                    getattr(discovered, "pk", None),
                )
                return False

            plugin_cls = get_manufacturer_plugin(manufacturer.code)
            if not plugin_cls:
                logger.warning("No plugin found for manufacturer %s", manufacturer.code)
                return False

            plugin = plugin_cls(manufacturer)

            device_data = self._get_device_data_from_plugin(plugin, discovered)
            if not device_data:
                logger.info(
                    "No device data found for discovered device %s (%s)",
                    getattr(discovered, "pk", None),
                    discovered.ip,
                )
                return False

            self._enrich_device_with_channels(plugin, discovered, device_data)

            transformed = self._transform_device(plugin, device_data, discovered)
            if not transformed:
                # Persist raw metadata to aid debugging
                discovered.metadata = device_data if isinstance(device_data, dict) else {}
                discovered.save()
                return False

            self._apply_transformed_to_discovered(discovered, transformed, device_data)
            discovered.save()
            return True

        except Exception:
            logger.exception(
                "Exception while refreshing discovered device %s",
                getattr(discovered, "pk", None),
            )
            return False

    def _get_device_data_from_plugin(self, plugin, discovered) -> dict | None:
        """Attempt to obtain raw device data from plugin using best-effort lookups."""
        # 1) Try direct lookup by API device id
        if discovered.api_device_id and hasattr(plugin, "get_device"):
            try:
                dev = plugin.get_device(discovered.api_device_id)
                if dev:
                    return dev
            except Exception:
                logger.debug(
                    "Plugin.get_device failed for %s (%s)",
                    discovered.api_device_id,
                    discovered.ip,
                )

        # 2) Fallback: fetch all devices and match by IP
        if hasattr(plugin, "get_devices"):
            try:
                devices = plugin.get_devices() or []
                for dev in devices:
                    if dev.get("ip") == discovered.ip or dev.get("ipAddress") == discovered.ip:
                        return dev
            except Exception:
                logger.debug(
                    "Plugin.get_devices failed for manufacturer %s",
                    plugin.manufacturer.code if hasattr(plugin, "manufacturer") else "unknown",
                )

        return None

    def _enrich_device_with_channels(self, plugin, discovered, device_data) -> None:
        """If available, fetch channel information and attach it to raw device_data."""
        if discovered.api_device_id and hasattr(plugin, "get_device_channels"):
            try:
                channels = plugin.get_device_channels(discovered.api_device_id)
                if channels is not None:
                    device_data["channels"] = channels
            except Exception:
                logger.debug("Could not fetch channels for device %s", discovered.api_device_id)

    def _transform_device(self, plugin, device_data, discovered) -> dict | None:
        """Transform raw device_data using manufacturer's plugin transformer."""
        try:
            if hasattr(plugin, "transform_device_data"):
                return plugin.transform_device_data(device_data)
        except Exception:
            logger.exception("Error transforming device data for %s", discovered.ip)
        return None

    def _apply_transformed_to_discovered(self, discovered, transformed, device_data) -> None:
        """Apply transformed/normalized device data onto the DiscoveredDevice model instance."""
        # Store raw metadata for debugging and traceability
        discovered.metadata = device_data if isinstance(device_data, dict) else transformed

        # Copy common fields if present
        model = transformed.get("model")
        if model:
            discovered.model = model

        api_id = transformed.get("api_device_id")
        if api_id:
            discovered.api_device_id = api_id

        ch = transformed.get("channels")
        if ch is not None:
            try:
                discovered.channels = int(ch)
            except Exception:
                pass

        # Map a few common status terms into our status enum if available
        status_val = transformed.get("status")
        if isinstance(status_val, str):
            ts = status_val.lower()
            if ts in ("online", "ready", "up"):
                discovered.status = discovered.STATUS_READY
            elif ts in ("offline", "down"):
                discovered.status = discovered.STATUS_OFFLINE
            elif ts in ("error", "fault"):
                discovered.status = discovered.STATUS_ERROR

    def promote_discovered_device(self, discovered) -> tuple[bool, str, object]:
        """Promote a discovered device to a managed WirelessChassis.

        Returns a tuple (success, message, chassis_or_none).
        This is a thin coordinator that delegates to smaller helpers to keep
        cyclomatic complexity low.
        """
        if not discovered.manufacturer:
            return (False, "No manufacturer specified for discovered device", None)

        existing = self._find_existing_chassis_for_discovered(discovered)
        if existing:
            return (False, f"Device already managed as chassis: {existing}", existing)

        try:
            plugin, device_data = self._get_plugin_and_device_data_for_promotion(discovered)
            if not plugin:
                return (False, "Plugin not available for manufacturer", None)

            if not device_data:
                chassis = self._create_basic_chassis_from_discovered(discovered)
                return (True, "Created basic chassis (limited API data)", chassis)

            return self._attempt_promotion_with_device_data(discovered, plugin, device_data)

        except Exception as e:
            logger.exception("Error promoting discovered device %s", discovered.ip)
            return (False, f"Exception during promotion: {e}", None)

    def _find_existing_chassis_for_discovered(self, discovered):
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(
            ip=discovered.ip, manufacturer=discovered.manufacturer
        ).first()

    def _get_plugin_and_device_data_for_promotion(self, discovered):
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        plugin = PluginRegistry.get_plugin(discovered.manufacturer.code, discovered.manufacturer)
        if not plugin:
            return None, None

        # Try to find matching device by IP
        try:
            api_devices = plugin.get_devices() or []
            for dev in api_devices:
                if dev.get("ip") == discovered.ip or dev.get("ipAddress") == discovered.ip:
                    return plugin, dev
        except Exception:
            logger.debug("Error fetching devices from plugin for promotion: %s", discovered.ip)

        return plugin, None

    def _create_basic_chassis_from_discovered(self, discovered):
        from micboard.models import WirelessChassis

        logger.warning(
            "Could not fetch detailed data for %s from API, creating basic chassis",
            discovered.ip,
        )
        return WirelessChassis.objects.create(
            manufacturer=discovered.manufacturer,
            api_device_id=discovered.ip,
            ip=discovered.ip,
            name=f"{discovered.device_type} at {discovered.ip}",
            model=discovered.device_type,
            role="receiver",
            max_channels=discovered.channels or 4,
            status="discovered",
        )

    def _attempt_promotion_with_device_data(
        self, discovered, plugin, device_data
    ) -> tuple[bool, str, object]:
        from micboard.services.manufacturer.manufacturer import ManufacturerService
        from micboard.services.sync.hardware_deduplication_service import (
            get_hardware_deduplication_service,
        )

        transformed = plugin.transform_device_data(device_data)
        if not transformed:
            return (False, "Failed to transform device data", None)

        dedup_service = get_hardware_deduplication_service(discovered.manufacturer)

        dedup_result = dedup_service.check_device(
            serial_number=transformed.get("serial_number"),
            mac_address=transformed.get("mac_address"),
            ip=transformed.get("ip"),
            api_device_id=transformed.get("api_device_id"),
            manufacturer=discovered.manufacturer,
        )

        if dedup_result.is_conflict:
            return (False, f"Device conflict: {dedup_result.conflict_reason}", None)

        if dedup_result.is_duplicate and dedup_result.existing_device:
            chassis = dedup_result.existing_device
            ManufacturerService._update_existing_chassis(
                chassis,
                ManufacturerService._normalize_devices([device_data], plugin)[0],
            )
            return (True, "Updated existing chassis", chassis)

        normalized = ManufacturerService._normalize_devices([device_data], plugin)
        if normalized:
            chassis = ManufacturerService._create_chassis(normalized[0], discovered.manufacturer)
            return (True, "Created new managed chassis", chassis)

        return (False, "Failed to normalize device data", None)
