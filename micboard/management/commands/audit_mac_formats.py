"""Management command that counts stored chassis MAC formats.

Prints totals only, never an address, so the output is safe to paste into a public issue.
Only ``WirelessChassis`` stores MAC addresses (``mac_address`` and ``mac_address_secondary``);
chargers and discovery records have no MAC field.

Usage:
    uv run --no-sync python manage.py audit_mac_formats
"""

from typing import Any

from django.core.management.base import BaseCommand

from micboard.services.hardware.dtos import MacFormatCounts
from micboard.services.hardware.mac_format_audit_service import MacFormatAuditService


class Command(BaseCommand):
    help = "Count stored chassis MAC addresses by format (read-only; prints totals only)"

    def handle(self, *args: Any, **options: Any) -> None:
        """Print the per-format totals for each stored MAC column."""
        result = MacFormatAuditService.audit()
        self._write_counts("WirelessChassis.mac_address", result.primary)
        self._write_counts("WirelessChassis.mac_address_secondary", result.secondary)

    def _write_counts(self, label: str, counts: MacFormatCounts) -> None:
        self.stdout.write(f"{label} (total: {counts.total})")
        for name in ("canonical", "legacy", "unmatched", "invalid", "blank"):
            self.stdout.write(f"  {name}: {getattr(counts, name)}")
