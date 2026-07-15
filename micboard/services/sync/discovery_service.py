"""Network discovery service to manage manufacturer IP/FQDN scans."""

import ipaddress
import logging
from collections.abc import Iterable
from itertools import batched, islice

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES, clamp_candidate_limit
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.common.base.plugin import ManufacturerPlugin
from micboard.services.sync.discovery_dtos import (
    DiscoveryCandidateSubmission,
    DiscoverySourceReconciliation,
)
from micboard.services.sync.discovery_utils import (
    collect_local_candidates,
    dedupe_preserve_order,
    get_manufacturer_plugin_instance,
    prepare_scanning_data,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Manages network discovery across all configured manufacturers."""

    @staticmethod
    def canonicalize_ip_addresses(
        ip_addresses: Iterable[object],
    ) -> tuple[list[str], int]:
        """Return stable canonical addresses and an invalid-item count."""
        canonical_addresses: list[str] = []
        rejected_count = 0
        for candidate in ip_addresses:
            if not isinstance(candidate, str):
                rejected_count += 1
                continue
            try:
                canonical_addresses.append(str(ipaddress.ip_address(candidate)))
            except ValueError:
                rejected_count += 1
        return list(dict.fromkeys(canonical_addresses)), rejected_count

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
        if conflicting_ips:
            logger.warning(
                "Skipping %d discovery candidates already managed by another manufacturer",
                len(conflicting_ips),
            )
        return conflicting_ips

    @staticmethod
    def _add_discovery_ips(
        plugin: ManufacturerPlugin,
        manufacturer: Manufacturer,
        ip_addresses: list[str],
    ) -> bool:
        """Add a discovery batch while containing vendor failures."""
        if not ip_addresses:
            return True

        logger.info(
            "Adding %d IPs to %s discovery list.",
            len(ip_addresses),
            manufacturer.code,
        )
        try:
            success = plugin.add_discovery_ips(ip_addresses)
        except Exception as exc:
            logger.exception(
                "Error adding discovery IPs for %s.",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )
            return False
        if not success:
            logger.warning("Failed to add discovery IPs for %s.", manufacturer.code)
        return success

    def add_discovery_candidates(
        self,
        manufacturer: Manufacturer,
        ip_addresses: Iterable[str],
        *,
        plugin: ManufacturerPlugin | None = None,
        batch_size: int = 1024,
    ) -> DiscoveryCandidateSubmission:
        """Submit deduplicated candidates in bounded batches after one ownership query."""
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        candidate_inputs = list(islice(ip_addresses, MAX_DISCOVERY_CANDIDATES + 1))
        if len(candidate_inputs) > MAX_DISCOVERY_CANDIDATES:
            raise ValueError(f"candidate count exceeds hard limit of {MAX_DISCOVERY_CANDIDATES}")
        unique_ips, rejected_count = self.canonicalize_ip_addresses(candidate_inputs)
        if not unique_ips:
            return DiscoveryCandidateSubmission(rejected_count=rejected_count)

        conflicting_ips = self._get_conflicting_ips(unique_ips, manufacturer)
        eligible_ips = [ip for ip in unique_ips if ip not in conflicting_ips]
        if not eligible_ips:
            return DiscoveryCandidateSubmission(
                failed_ips=[ip for ip in unique_ips if ip in conflicting_ips],
                rejected_count=rejected_count,
            )

        discovery_plugin = plugin or get_manufacturer_plugin_instance(manufacturer)
        submitted: set[str] = set()
        failed = set(conflicting_ips)
        for candidate_batch in batched(eligible_ips, batch_size, strict=False):
            batch = list(candidate_batch)
            if self._add_discovery_ips(discovery_plugin, manufacturer, batch):
                submitted.update(batch)
            else:
                failed.update(batch)
        return DiscoveryCandidateSubmission(
            submitted_ips=[ip for ip in unique_ips if ip in submitted],
            failed_ips=[ip for ip in unique_ips if ip in failed],
            rejected_count=rejected_count,
        )

    @staticmethod
    def _remove_discovery_ips(
        plugin: ManufacturerPlugin,
        manufacturer: Manufacturer,
        ip_addresses: list[str],
    ) -> bool:
        """Remove a discovery batch while containing vendor failures."""
        if not ip_addresses:
            return True

        logger.info(
            "Removing %d IPs from %s discovery list.",
            len(ip_addresses),
            manufacturer.code,
        )
        try:
            success = plugin.remove_discovery_ips(ip_addresses)
        except Exception as exc:
            logger.exception(
                "Error removing discovery IPs for %s.",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )
            return False
        if not success:
            logger.warning("Failed to remove discovery IPs for %s.", manufacturer.code)
        return success

    def run_manufacturer_discovery(
        self,
        manufacturer: Manufacturer,
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
    ) -> DiscoverySourceReconciliation:
        """Runs discovery for a single manufacturer."""
        candidate_limit = clamp_candidate_limit(max_hosts)
        # Build desired state from locally managed chassis and configured scan sources.
        candidate_ips, local_sources_complete = collect_local_candidates(
            manufacturer,
            limit=candidate_limit,
        )
        scan_limit = candidate_limit - len(candidate_ips)

        # Prepare scanning data for CIDRs and FQDNs
        cidr_hosts_map, fqdns_map, _, scan_sources_complete = prepare_scanning_data(
            manufacturer,
            scan_cidrs,
            scan_fqdns,
            scan_limit,
        )
        sources_complete = local_sources_complete and scan_sources_complete

        # Add CIDR hosts to candidates
        for hosts in cidr_hosts_map.values():
            candidate_ips.extend(hosts)

        # Add FQDN resolved IPs to candidates
        for hosts in fqdns_map.values():
            candidate_ips.extend(hosts)

        # Dedupe while preserving order
        unique_candidate_ips, rejected_local_candidates = self.canonicalize_ip_addresses(
            candidate_ips
        )
        sources_complete = sources_complete and rejected_local_candidates == 0
        logger.info(
            "Manufacturer %s: Found %d unique candidate IPs from local sources.",
            manufacturer.code,
            len(unique_candidate_ips),
        )

        plugin = get_manufacturer_plugin_instance(manufacturer)
        existing_discovery_ips: list[str] = []
        remote_source_complete = True
        try:
            remote_candidates = plugin.get_discovery_ips() or []
            raw_remote_candidates = list(
                islice(iter(remote_candidates), MAX_DISCOVERY_CANDIDATES + 1)
            )
            string_remote_candidates = [
                candidate
                for candidate in raw_remote_candidates[:MAX_DISCOVERY_CANDIDATES]
                if isinstance(candidate, str)
            ]
            existing_discovery_ips, rejected_remote_candidates = self.canonicalize_ip_addresses(
                string_remote_candidates
            )
            remote_payload_valid = (
                len(string_remote_candidates)
                == len(raw_remote_candidates[:MAX_DISCOVERY_CANDIDATES])
                and rejected_remote_candidates == 0
            )
            if len(raw_remote_candidates) > MAX_DISCOVERY_CANDIDATES or not remote_payload_valid:
                remote_source_complete = False
                logger.warning(
                    "Manufacturer %s returned incomplete discovery state; "
                    "reconciling only the valid bounded prefix of %d items.",
                    manufacturer.code,
                    MAX_DISCOVERY_CANDIDATES,
                )
        except Exception as exc:
            remote_source_complete = False
            logger.exception(
                "Could not retrieve existing discovery IPs for %s",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )

        reconciliation_ips = dedupe_preserve_order([*unique_candidate_ips, *existing_discovery_ips])
        conflicting_ips = self._get_conflicting_ips(reconciliation_ips, manufacturer)
        eligible_candidates = [ip for ip in unique_candidate_ips if ip not in conflicting_ips]
        existing_ip_set = set(existing_discovery_ips)
        candidate_ip_set = set(eligible_candidates)
        ips_to_add = [ip for ip in eligible_candidates if ip not in existing_ip_set]
        ips_to_remove = (
            [ip for ip in existing_discovery_ips if ip not in candidate_ip_set]
            if sources_complete and remote_source_complete
            else [ip for ip in existing_discovery_ips if ip in conflicting_ips]
        )

        additions_succeeded = self._add_discovery_ips(plugin, manufacturer, ips_to_add)
        removals_succeeded = self._remove_discovery_ips(plugin, manufacturer, ips_to_remove)

        logger.info("Finished discovery for manufacturer: %s", manufacturer.name)
        success = (
            additions_succeeded
            and removals_succeeded
            and sources_complete
            and remote_source_complete
        )
        return DiscoverySourceReconciliation(
            manufacturer=manufacturer.pk,
            success=success,
            sources_complete=sources_complete,
            remote_source_complete=remote_source_complete,
            additions_succeeded=additions_succeeded,
            removals_succeeded=removals_succeeded,
        )
