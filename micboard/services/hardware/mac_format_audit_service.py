"""Read-only census of how chassis MAC addresses are stored."""

from collections.abc import Iterable

from django.db import DEFAULT_DB_ALIAS

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.dtos import MacFormatAuditResult, MacFormatCounts
from micboard.utils.mac_address import canonicalize_mac_address, mac_address_query_variants


class MacFormatAuditService:
    """Count stored MACs by format without retaining or exposing any address."""

    @classmethod
    def audit(cls, *, using: str = DEFAULT_DB_ALIAS) -> MacFormatAuditResult:
        """Classify the primary and secondary chassis MAC columns."""
        manager = WirelessChassis._default_manager.using(using)
        return MacFormatAuditResult(
            primary=cls._count(manager.values_list("mac_address", flat=True).iterator(2000)),
            secondary=cls._count(
                manager.values_list("mac_address_secondary", flat=True).iterator(2000)
            ),
        )

    @staticmethod
    def _count(stored: Iterable[str | None]) -> MacFormatCounts:
        """Bucket each value.

        ``legacy`` means a form that ``mac_address_query_variants`` still matches; a valid
        address outside those variants (mixed case, padding) is ``unmatched``.
        """
        counts = {"canonical": 0, "legacy": 0, "unmatched": 0, "invalid": 0, "blank": 0}
        for value in stored:
            if value is None or not value.strip():
                counts["blank"] += 1
            elif canonicalize_mac_address(value) is None:
                counts["invalid"] += 1
            elif value == canonicalize_mac_address(value):
                counts["canonical"] += 1
            elif value in mac_address_query_variants(value):
                counts["legacy"] += 1
            else:
                counts["unmatched"] += 1
        return MacFormatCounts(total=sum(counts.values()), **counts)
