"""Read-only census of how chassis MAC addresses are stored."""

from django.db import DEFAULT_DB_ALIAS

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.dtos import MacFormatAuditResult
from micboard.utils.mac_address import canonicalize_mac_address


class MacFormatAuditService:
    """Count stored MACs by format without retaining or exposing any address."""

    @staticmethod
    def audit(*, using: str = DEFAULT_DB_ALIAS) -> MacFormatAuditResult:
        """Classify every chassis MAC as canonical, legacy, invalid, or blank."""
        counts = {"canonical": 0, "legacy": 0, "invalid": 0, "blank": 0}
        stored = (
            WirelessChassis._default_manager.using(using)
            .values_list("mac_address", flat=True)
            .iterator(chunk_size=2000)
        )
        for value in stored:
            if value is None or not value.strip():
                counts["blank"] += 1
                continue
            canonical = canonicalize_mac_address(value)
            if canonical is None:
                counts["invalid"] += 1
            elif canonical == value:
                counts["canonical"] += 1
            else:
                counts["legacy"] += 1
        return MacFormatAuditResult(total=sum(counts.values()), **counts)
