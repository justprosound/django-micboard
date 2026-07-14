"""Management command to check and display real-time connection status."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from micboard.models.realtime.connection import RealTimeConnection
from micboard.services.realtime.connection_service import connection_duration
from micboard.tasks.monitoring.health import get_realtime_connection_status


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
        self._write_summary(summary)

        connections = self._get_connections(manufacturer_code, status_filter)
        if not connections.exists():
            self.stdout.write("\nNo connections found matching the criteria.")
            return
        if verbose:
            self._write_verbose_connections(connections)

    def _write_summary(self, summary) -> None:
        self.stdout.write("Real-Time Connection Status Summary:")
        self.stdout.write("-" * 40)
        self.stdout.write(f"Total connections: {summary['total']}")
        self.stdout.write(f"Connected: {summary['connected']}")
        self.stdout.write(f"Connecting: {summary['connecting']}")
        self.stdout.write(f"Disconnected: {summary['disconnected']}")
        self.stdout.write(f"Errors: {summary['error']}")
        self.stdout.write(f"Stopped: {summary['stopped']}")
        self.stdout.write(f"Healthy: {summary['healthy_percentage']:.1f}%")

    @staticmethod
    def _get_connections(manufacturer_code, status_filter):
        connections = RealTimeConnection.objects.select_related("chassis", "chassis__manufacturer")
        if manufacturer_code:
            connections = connections.filter(chassis__manufacturer__code=manufacturer_code)
        if status_filter:
            connections = connections.filter(status=status_filter)
        return connections.order_by("chassis__manufacturer__name", "chassis__name")

    def _write_verbose_connections(self, connections) -> None:
        self.stdout.write("\nDetailed Connection Status:")
        self.stdout.write("-" * 80)
        for connection in connections:
            self._write_connection(connection)

    def _write_connection(self, connection) -> None:
        styled_status = self._style_status(connection.status)
        self.stdout.write(
            f"{connection.chassis.manufacturer.name} - {connection.chassis.name}: {styled_status}"
        )
        details = (
            ("Connected", connection.connected_at),
            ("Last message", connection.last_message_at),
            ("Error", connection.error_message),
            ("Duration", connection_duration(connection)),
        )
        for label, value in details:
            if value:
                self.stdout.write(f"  {label}: {value}")
        self.stdout.write("")

    def _style_status(self, status: str) -> str:
        """Apply command-line styling to a connection status."""
        label = status.upper()
        return {
            "connected": self.style.SUCCESS,
            "connecting": self.style.WARNING,
            "disconnected": self.style.WARNING,
            "error": self.style.ERROR,
        }.get(status, lambda value: value)(label)
