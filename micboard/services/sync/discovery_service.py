"""Network discovery service to manage manufacturer IP/FQDN scans."""

import logging
from typing import cast

from micboard.discovery.network_utils import expand_cidrs, resolve_fqdns
from micboard.integrations.common import get_manufacturer_plugin
from micboard.integrations.common.base import BaseAPIClient
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


def get_manufacturer_client(manufacturer: Manufacturer) -> BaseAPIClient:
    """Get the API client for a given manufacturer."""
    plugin_class = get_manufacturer_plugin(manufacturer.code)
    plugin = plugin_class(manufacturer)
    return plugin.get_client()


class DiscoveryService:
    """Manages network discovery across all configured manufacturers."""

    def _get_manufacturer_client(self, manufacturer: Manufacturer) -> BaseAPIClient:
        return get_manufacturer_client(manufacturer)

    def _is_ip_managed_by_another_manufacturer(
        self, ip_address: str, current_manufacturer: Manufacturer
    ) -> bool:
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
            self.run_manufacturer_discovery(manufacturer, scan_cidrs, scan_fqdns, max_hosts)

    @staticmethod
    def trigger_manufacturer_discovery(
        manufacturer_pk: int, scan_cidrs: bool = True, scan_fqdns: bool = True
    ) -> None:
        from micboard.utils.dependencies import HAS_DJANGO_Q

        if not manufacturer_pk:
            return

        if HAS_DJANGO_Q:
            try:
                from django_q.tasks import async_task

                from micboard.tasks.sync.discovery import run_manufacturer_discovery_task

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

        try:
            ds = DiscoveryService()
            manufacturer = Manufacturer.objects.get(pk=manufacturer_pk)
            ds.run_manufacturer_discovery(manufacturer, scan_cidrs, scan_fqdns, max_hosts=1024)
        except Exception:
            logger.exception(
                "Failed to run discovery synchronously for manufacturer %s",
                manufacturer_pk,
            )

    def run_manufacturer_discovery(
        self,
        manufacturer: Manufacturer,
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
    ):
        """Runs discovery for a single manufacturer."""
        candidate_ips: list[str] = []

        chassis_ips = (
            WirelessChassis.objects.filter(manufacturer=manufacturer)
            .exclude(ip__isnull=True)
            .exclude(ip="")
            .values_list("ip", flat=True)
        )
        candidate_ips.extend(chassis_ips)

        if scan_cidrs:
            cidrs = [dc.cidr for dc in DiscoveryCIDR.objects.filter(manufacturer=manufacturer)]
            for ip in expand_cidrs(cidrs, max_hosts=max_hosts):
                candidate_ips.append(ip)

        if scan_fqdns:
            fqdns = [df.fqdn for df in DiscoveryFQDN.objects.filter(manufacturer=manufacturer)]
            resolved_fqdns = resolve_fqdns(fqdns)
            for _, ips in resolved_fqdns.items():
                candidate_ips.extend(ips)

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
