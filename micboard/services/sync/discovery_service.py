"""Network discovery service to manage manufacturer IP/FQDN scans."""

import logging

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.common.base.plugin import ManufacturerPlugin
from micboard.services.sync.discovery_utils import (
    collect_local_candidates,
    dedupe_preserve_order,
    get_manufacturer_plugin_instance,
    is_ip_managed_by_another_manufacturer,
    prepare_scanning_data,
)

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Manages network discovery across all configured manufacturers."""

    def _get_manufacturer_plugin(self, manufacturer: Manufacturer) -> ManufacturerPlugin:
        return get_manufacturer_plugin_instance(manufacturer)

    def _is_ip_managed_by_another_manufacturer(
        self,
        ip_address: str,
        current_manufacturer: Manufacturer,
        *,
        using: str = "default",
    ) -> bool:
        return is_ip_managed_by_another_manufacturer(
            ip_address,
            current_manufacturer,
            using=using,
        )

    def add_discovery_candidate(
        self,
        ip_address: str,
        manufacturer: Manufacturer,
        source: str = "manual",
        *,
        using: str = "default",
    ) -> bool:
        """Adds an IP address to a manufacturer's discovery list, enforcing exclusivity."""
        if self._is_ip_managed_by_another_manufacturer(
            ip_address,
            manufacturer,
            using=using,
        ):
            logger.warning(
                "IP %s is already managed by another manufacturer. Skipping for %s.",
                ip_address,
                manufacturer.code,
            )
            return False

        plugin = self._get_manufacturer_plugin(manufacturer)
        try:
            success = plugin.add_discovery_ips([ip_address])
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
            logger.exception(
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
        plugin = self._get_manufacturer_plugin(manufacturer)
        try:
            success = plugin.remove_discovery_ips([ip_address])
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

    @staticmethod
    def _get_conflicting_ips(
        ip_addresses: list[str],
        manufacturer: Manufacturer,
    ) -> set[str]:
        """Return addresses already owned by another manufacturer."""
        if not ip_addresses:
            return set()

        conflicting_ips = set(
            WirelessChassis.objects.filter(ip__in=ip_addresses)
            .exclude(manufacturer=manufacturer)
            .values_list("ip", flat=True)
        )
        for ip_address in conflicting_ips:
            logger.warning(
                "IP %s is already managed by another manufacturer. Skipping for %s.",
                ip_address,
                manufacturer.code,
            )
        return conflicting_ips

    @staticmethod
    def _add_discovery_ips(
        plugin: ManufacturerPlugin,
        manufacturer: Manufacturer,
        ip_addresses: list[str],
    ) -> None:
        """Add a discovery batch while containing vendor failures."""
        if not ip_addresses:
            return

        logger.info(
            "Adding %d IPs to %s discovery list.",
            len(ip_addresses),
            manufacturer.code,
        )
        try:
            success = plugin.add_discovery_ips(ip_addresses)
        except Exception:
            logger.exception("Error adding discovery IPs for %s.", manufacturer.code)
            return
        if not success:
            logger.warning("Failed to add discovery IPs for %s.", manufacturer.code)

    @staticmethod
    def _remove_discovery_ips(
        plugin: ManufacturerPlugin,
        manufacturer: Manufacturer,
        ip_addresses: list[str],
    ) -> None:
        """Remove a discovery batch while containing vendor failures."""
        if not ip_addresses:
            return

        logger.info(
            "Removing %d IPs from %s discovery list.",
            len(ip_addresses),
            manufacturer.code,
        )
        try:
            success = plugin.remove_discovery_ips(ip_addresses)
        except Exception:
            logger.exception("Error removing discovery IPs for %s.", manufacturer.code)
            return
        if not success:
            logger.warning("Failed to remove discovery IPs for %s.", manufacturer.code)

    def run_global_discovery(
        self, scan_cidrs: bool = True, scan_fqdns: bool = True, max_hosts: int = 1024
    ):
        """Runs discovery across all configured manufacturers."""
        manufacturers = Manufacturer.objects.all()
        for manufacturer in manufacturers:
            logger.info("Starting discovery for manufacturer: %s", manufacturer.name)
            self.run_manufacturer_discovery(manufacturer, scan_cidrs, scan_fqdns, max_hosts)

    def run_manufacturer_discovery(
        self,
        manufacturer: Manufacturer,
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
    ):
        """Runs discovery for a single manufacturer."""
        # Build desired state from locally managed chassis and configured scan sources.
        candidate_ips = collect_local_candidates(manufacturer)

        # Prepare scanning data for CIDRs and FQDNs
        cidr_hosts_map, fqdns_map, _, sources_complete = prepare_scanning_data(
            manufacturer, scan_cidrs, scan_fqdns, max_hosts
        )

        # Add CIDR hosts to candidates
        for hosts in cidr_hosts_map.values():
            candidate_ips.extend(hosts)

        # Add FQDN resolved IPs to candidates
        for hosts in fqdns_map.values():
            candidate_ips.extend(hosts)

        # Dedupe while preserving order
        unique_candidate_ips = dedupe_preserve_order(candidate_ips)
        logger.info(
            "Manufacturer %s: Found %d unique candidate IPs from local sources.",
            manufacturer.code,
            len(unique_candidate_ips),
        )

        plugin = self._get_manufacturer_plugin(manufacturer)
        existing_discovery_ips = []
        try:
            existing_discovery_ips = plugin.get_discovery_ips() or []
        except Exception as e:
            logger.warning(
                "Could not retrieve existing discovery IPs for %s: %s",
                manufacturer.code,
                e,
            )

        reconciliation_ips = dedupe_preserve_order([*unique_candidate_ips, *existing_discovery_ips])
        conflicting_ips = self._get_conflicting_ips(reconciliation_ips, manufacturer)
        eligible_candidates = [ip for ip in unique_candidate_ips if ip not in conflicting_ips]
        existing_ip_set = set(existing_discovery_ips)
        candidate_ip_set = set(eligible_candidates)
        ips_to_add = [ip for ip in eligible_candidates if ip not in existing_ip_set]
        ips_to_remove = (
            [ip for ip in existing_discovery_ips if ip not in candidate_ip_set]
            if sources_complete
            else [ip for ip in existing_discovery_ips if ip in conflicting_ips]
        )

        self._add_discovery_ips(plugin, manufacturer, ips_to_add)
        self._remove_discovery_ips(plugin, manufacturer, ips_to_remove)

        logger.info("Finished discovery for manufacturer: %s", manufacturer.name)

    def get_all_managed_ips(self) -> set[str]:
        """Returns a set of all IP addresses currently managed by any manufacturer."""
        return set(WirelessChassis.objects.exclude(ip__isnull=True).values_list("ip", flat=True))

    def get_manufacturer_for_ip(self, ip_address: str) -> Manufacturer | None:
        """Returns the manufacturer managing a given IP address, if any."""
        try:
            chassis = WirelessChassis.objects.filter(ip=ip_address).first()
            if chassis:
                return chassis.manufacturer
        except Exception as e:
            logger.error("Error getting manufacturer for IP %s: %s", ip_address, e)
        return None
