"""Submit validated IP addresses to a manufacturer's discovery workflow."""

from __future__ import annotations

import ipaddress
import re
from itertools import islice
from typing import Any

from django.core.management.base import BaseCommand

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.sync.discovery_service import DiscoveryService


class Command(BaseCommand):
    """Validate operator-supplied addresses and submit them through the service layer."""

    help = "Add device IP addresses to a manufacturer's discovery candidates"

    def add_arguments(self, parser: Any) -> None:
        """Register bounded discovery candidate options."""
        parser.add_argument(
            "--ips",
            type=str,
            required=True,
            help="Comma-separated device IP addresses",
        )
        parser.add_argument(
            "--manufacturer",
            type=str,
            default="shure",
            help="Manufacturer code (default: shure)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Submit a bounded, canonical address list without direct network probing."""
        manufacturer_code = str(options["manufacturer"])
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Manufacturer '{manufacturer_code}' not found"))
            return

        raw_addresses = list(
            islice(
                (match.group(0).strip() for match in re.finditer(r"[^,]+", options["ips"])),
                MAX_DISCOVERY_CANDIDATES + 1,
            )
        )
        if len(raw_addresses) > MAX_DISCOVERY_CANDIDATES:
            self.stderr.write(
                self.style.ERROR(
                    f"Candidate count exceeds hard limit of {MAX_DISCOVERY_CANDIDATES}"
                )
            )
            return

        canonical_addresses: list[str] = []
        invalid_count = 0
        for raw_address in raw_addresses:
            try:
                canonical_addresses.append(str(ipaddress.ip_address(raw_address)))
            except ValueError:
                invalid_count += 1
        canonical_addresses = list(dict.fromkeys(canonical_addresses))
        if not canonical_addresses:
            self.stderr.write(self.style.ERROR("No valid IP addresses provided"))
            return

        submission = DiscoveryService().add_discovery_candidates(
            manufacturer,
            canonical_addresses,
        )
        rejected_count = invalid_count + submission.rejected_count + len(submission.failed_ips)
        self.stdout.write(
            self.style.SUCCESS(
                f"Submitted {len(submission.submitted_ips)} discovery candidates; "
                f"rejected {rejected_count}"
            )
        )
