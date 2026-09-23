"""Management command that seeds the demonstration dataset."""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand

from micboard.services.demo.seed_service import DemoSeedService


class Command(BaseCommand):
    """Create a small, self-consistent demonstration dataset."""

    help = (
        "Seed demonstration hardware, locations, assignments, and telemetry. "
        "Safe to run repeatedly; a second run creates nothing."
    )

    def add_arguments(self, parser: Any) -> None:
        """Register the optional read-only account password."""
        parser.add_argument(
            "--read-only-password",
            default=os.environ.get("MICBOARD_DEMO_PASSWORD"),
            help=(
                "Password for the read-only 'demo' staff account. Also read from "
                "MICBOARD_DEMO_PASSWORD. The account is not created without it."
            ),
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        """Delegate to the seeding service and report what it produced."""
        summary = DemoSeedService().seed(read_only_password=options["read_only_password"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded the demo fixture: {summary.units} transmitter(s), "
                f"{summary.telemetry_samples} telemetry sample(s)"
            )
        )
        if summary.read_only_user_created:
            self.stdout.write(self.style.SUCCESS("Created the read-only 'demo' account"))
        elif options["read_only_password"]:
            self.stdout.write("Reset the password on the existing read-only 'demo' account")
        else:
            self.stdout.write(
                self.style.WARNING(
                    "No read-only password supplied; the 'demo' account was not created"
                )
            )
