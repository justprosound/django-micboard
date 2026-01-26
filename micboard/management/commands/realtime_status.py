"""Management command to check and display real-time connection status."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from micboard.models import RealTimeConnection
from micboard.tasks.health_tasks import get_realtime_connection_status


class Command(BaseCommand):
    help = "Check and display real-time connection status"

    def add_arguments(self, parser):
        parser.add_argument(
            "--manufacturer",
            type=str,
            help="Filter by manufacturer code",
        )
        parser.add_argument(
            "--status",
            type=str,
            choices=["connected", "connecting", "disconnected", "error", "stopped"],
            help="Filter by connection status",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed information for each connection",
        )

    def handle(self, *args, **options):
        manufacturer_code = options.get("manufacturer")
        status_filter = options.get("status")
        verbose = options.get("verbose")

        # Get summary
        summary = get_realtime_connection_status()
        if "error" in summary and isinstance(summary["error"], str):
            self.stderr.write(self.style.ERROR(f"Error getting status: {summary['error']}"))
            return

        self.stdout.write("Real-Time Connection Status Summary:")
        self.stdout.write("-" * 40)
        self.stdout.write(f"Total connections: {summary['total']}")
        self.stdout.write(f"Connected: {summary['connected']}")
        self.stdout.write(f"Connecting: {summary['connecting']}")
        self.stdout.write(f"Disconnected: {summary['disconnected']}")
        self.stdout.write(f"Errors: {summary['error']}")
        self.stdout.write(f"Stopped: {summary['stopped']}")
        self.stdout.write(f"Healthy: {summary['healthy_percentage']:.1f}%")

        # Get detailed connections
        connections = RealTimeConnection.objects.select_related(
            "receiver", "receiver__manufacturer"
        )

        if manufacturer_code:
            connections = connections.filter(receiver__manufacturer__code=manufacturer_code)

        if status_filter:
            connections = connections.filter(status=status_filter)

        connections = connections.order_by("receiver__manufacturer__name", "receiver__name")

        if not connections.exists():
            self.stdout.write("\nNo connections found matching the criteria.")
            return

        if verbose:
            self.stdout.write("\nDetailed Connection Status:")
            self.stdout.write("-" * 80)

            for conn in connections:
                status_color = self._get_status_color(conn.status)
                self.stdout.write(
                    f"{conn.receiver.manufacturer.name} - {conn.receiver.name}: "
                    f"{status_color}{conn.status.upper()}{self.style.RESET_ALL}"
                )

                if conn.connected_at:
                    self.stdout.write(f"  Connected: {conn.connected_at}")
                if conn.last_message_at:
                    self.stdout.write(f"  Last message: {conn.last_message_at}")
                if conn.error_message:
                    self.stdout.write(f"  Error: {conn.error_message}")
                if conn.connection_duration:
                    duration = conn.connection_duration
                    self.stdout.write(f"  Duration: {duration}")
                self.stdout.write("")  # Empty line between connections

    def _get_status_color(self, status):
        """Get color styling for connection status."""
        if status == "connected":
            return self.style.SUCCESS
        elif status == "connecting":
            return self.style.WARNING
        elif status == "error":
            return self.style.ERROR
        elif status == "disconnected":
            return self.style.WARNING
        else:
            return self.style.RESET_ALL
