"""CLI tools and management commands helpers for django-micboard.

Provides utilities and helpers for creating management commands.
"""

from __future__ import annotations

from typing import Any, Dict, List

from django.core.management.base import BaseCommand

from micboard.services import (
    ConnectionHealthService,
    HardwareService,
    ManufacturerService,
)


class ServiceCommandMixin:
    """Mixin for management commands that use services."""

    def print_section(self, title: str) -> None:
        """Print a section header.

        Args:
            title: Section title.
        """
        self.stdout.write(f"\n{'=' * 60}")  # type: ignore[attr-defined]
        self.stdout.write(f"  {title}")  # type: ignore[attr-defined]
        self.stdout.write(f"{'=' * 60}\n")  # type: ignore[attr-defined]

    def print_success(self, message: str) -> None:
        """Print success message.

        Args:
            message: Success message.
        """
        self.stdout.write(self.style.SUCCESS(f"✓ {message}"))  # type: ignore[attr-defined]

    def print_error(self, message: str) -> None:
        """Print error message.

        Args:
            message: Error message.
        """
        self.stdout.write(self.style.ERROR(f"✗ {message}"))  # type: ignore[attr-defined]

    def print_warning(self, message: str) -> None:
        """Print warning message.

        Args:
            message: Warning message.
        """
        self.stdout.write(self.style.WARNING(f"⚠ {message}"))  # type: ignore[attr-defined]

    def print_info(self, message: str) -> None:
        """Print info message.

        Args:
            message: Info message.
        """
        self.stdout.write(self.style.HTTP_INFO(f"ℹ {message}"))  # type: ignore[attr-defined]

    def print_table(self, rows: List[List[str]], headers: List[str]) -> None:
        """Print formatted table.

        Args:
            rows: List of row data.
            headers: Column headers.
        """
        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))

        # Print header
        header_row = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        self.stdout.write(self.style.HTTP_INFO(header_row))  # type: ignore[attr-defined]
        self.stdout.write("-" * len(header_row))  # type: ignore[attr-defined]

        # Print rows
        for row in rows:
            row_str = " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
            self.stdout.write(row_str)  # type: ignore[attr-defined]


class SyncDevicesCommand(ServiceCommandMixin, BaseCommand):
    """Example management command for syncing devices."""

    help = "Sync devices from manufacturer APIs"

    def add_arguments(self, parser) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--manufacturer",
            help="Specific manufacturer to sync (e.g., shure)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Verbose output",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Handle command execution."""
        self.print_section("Device Sync")

        manufacturers = (
            options.get("manufacturer") and [options["manufacturer"]] or ["shure", "sennheiser"]
        )

        total_synced = 0
        total_errors = 0

        for manufacturer_code in manufacturers:
            try:
                self.print_info(f"Syncing devices for {manufacturer_code}...")

                result = ManufacturerService.sync_devices_for_manufacturer(
                    manufacturer_code=manufacturer_code
                )

                synced = result.get("devices_synced", 0)
                total_synced += synced

                self.print_success(f"Synced {synced} devices from {manufacturer_code}")

            except Exception as e:
                total_errors += 1
                self.print_error(f"Error syncing {manufacturer_code}: {e}")

        self.print_section("Summary")
        self.print_success(f"Total synced: {total_synced}")
        if total_errors > 0:
            self.print_warning(f"Errors: {total_errors}")


class HealthCheckCommand(ServiceCommandMixin, BaseCommand):
    """Example management command for health checks."""

    help = "Check system health"

    def handle(self, *args: Any, **options: Any) -> None:
        """Handle command execution."""
        self.print_section("System Health Check")

        # Check connections
        self.print_info("Checking manufacturer connections...")
        unhealthy = ConnectionHealthService.get_unhealthy_connections()

        if not unhealthy:
            self.print_success("All manufacturer connections are healthy")
        else:
            self.print_warning(f"{len(unhealthy)} unhealthy connections found:")
            for conn in unhealthy:
                self.print_warning(f"  - {conn.get('manufacturer_code')}")

        # Check devices
        self.print_info("Checking device status...")
        active_receivers = HardwareService.get_active_receivers()
        online_count = active_receivers.filter(is_online=True).count()
        offline_count = active_receivers.filter(is_online=False).count()

        self.print_info(f"Total active receivers: {active_receivers.count()}")
        self.print_success(f"Online: {online_count}")
        self.print_warning(f"Offline: {offline_count}")

        # Check low battery
        low_battery = HardwareService.get_low_battery_receivers(threshold=20)
        if low_battery.count() > 0:
            self.print_warning(f"Low battery devices: {low_battery.count()}")

        self.print_section("Health Check Complete")


class ReportCommand(ServiceCommandMixin, BaseCommand):
    """Example management command for generating reports."""

    help = "Generate system reports"

    def add_arguments(self, parser) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--type",
            choices=["devices", "health", "all"],
            default="all",
            help="Report type",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Handle command execution."""
        report_type = options["type"]

        if report_type in ["devices", "all"]:
            self._device_report()

        if report_type in ["health", "all"]:
            self._health_report()

    def _device_report(self) -> None:
        """Generate device report."""
        self.print_section("Device Report")

        active_receivers = HardwareService.get_active_receivers()

        rows = []
        for device in active_receivers[:10]:  # Top 10
            status = "Online" if device.is_online else "Offline"
            # Chassis doesn't have battery_level
            battery = "N/A"
            rows.append([device.name, status, battery])

        self.print_table(rows, ["Device Name", "Status", "Battery"])

    def _health_report(self) -> None:
        """Generate health report."""
        self.print_section("Health Report")

        unhealthy = ConnectionHealthService.get_unhealthy_connections()

        if not unhealthy:
            self.print_success("All connections are healthy")
        else:
            rows = [[conn.get("manufacturer_code"), "Unhealthy"] for conn in unhealthy]
            self.print_table(rows, ["Manufacturer", "Status"])


class CommandHelper:
    """Helper utilities for management commands."""

    @staticmethod
    def confirm_action(question: str, *, default: bool = False) -> bool:
        """Ask user for confirmation.

        Args:
            question: Confirmation question.
            default: Default answer if user presses enter.

        Returns:
            True if confirmed, False otherwise.
        """
        valid_answers = {"y": True, "n": False}
        default_answer = "y" if default else "n"

        prompt = f"{question} [{default_answer}]: "

        while True:
            answer = input(prompt).lower() or default_answer
            if answer in valid_answers:
                return valid_answers[answer]
            print("Please answer 'y' or 'n'")

    @staticmethod
    def progress_bar(current: int, total: int, width: int = 40) -> str:
        """Generate progress bar string.

        Args:
            current: Current progress.
            total: Total items.
            width: Bar width in characters.

        Returns:
            Progress bar string.
        """
        percent = current / total
        filled = int(width * percent)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {percent * 100:.1f}%"

    @staticmethod
    def get_user_choice(options: Dict[str, str]) -> str:
        """Get user choice from options.

        Args:
            options: Dictionary of choice: description.

        Returns:
            Selected choice key.
        """
        for i, (_key, desc) in enumerate(options.items(), 1):
            print(f"{i}. {desc}")

        while True:
            try:
                choice = int(input("Select option: "))
                if 1 <= choice <= len(options):
                    return list(options.keys())[choice - 1]
            except ValueError:
                pass

            print("Invalid choice")
