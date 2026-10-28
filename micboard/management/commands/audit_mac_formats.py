"""Management command that counts stored chassis MAC formats.

Prints totals only, never an address, so the output is safe to paste into a public issue.

Usage:
    uv run --no-sync python manage.py audit_mac_formats
"""

from typing import Any

from django.core.management.base import BaseCommand

from micboard.services.hardware.mac_format_audit_service import MacFormatAuditService


class Command(BaseCommand):
    help = "Count stored chassis MAC addresses by format (read-only; prints totals only)"

    def handle(self, *args: Any, **options: Any) -> None:
        """Print the per-format totals."""
        result = MacFormatAuditService.audit()
        self.stdout.write(f"WirelessChassis MAC formats (total: {result.total})")
        self.stdout.write(f"  canonical: {result.canonical}")
        self.stdout.write(f"  legacy: {result.legacy}")
        self.stdout.write(f"  invalid: {result.invalid}")
        self.stdout.write(f"  blank: {result.blank}")
