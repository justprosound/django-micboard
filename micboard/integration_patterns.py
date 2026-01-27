"""Common integration patterns and helpers for django-micboard services.

Provides ready-to-use patterns for common use cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from micboard.services import (
    AssignmentService,
    ConnectionHealthService,
    HardwareService,
    DiscoveryService,
    LocationService,
    ManufacturerService,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from micboard.models import WirelessChassis, WirelessUnit


class BulkOperationPattern:
    """Pattern for bulk operations using services."""

    @staticmethod
    def bulk_sync_device_status(
        *, devices: list[WirelessChassis | WirelessUnit], online: bool
    ) -> dict[str, int]:
        """Bulk sync device status.

        Args:
            devices: List of devices to sync.
            online: Online status to set.

        Returns:
            Dictionary with sync statistics.
        """
        synced = 0
        failed = 0

        for device in devices:
            try:
                HardwareService.sync_device_status(device_obj=device, online=online)
                synced += 1
            except Exception:
                failed += 1

        return {"synced": synced, "failed": failed}

    @staticmethod
    def bulk_create_assignments(
        *, user: User, receivers: list[WirelessChassis], alert_enabled: bool = False
    ) -> dict[str, int]:
        """Bulk create assignments for user across receivers (first channel only)."""
        created = 0
        skipped = 0

        for receiver in receivers:
            channel = receiver.rf_channels.first()
            if channel is None:
                skipped += 1
                continue

            try:
                AssignmentService.create_assignment(
                    user=user, channel=channel, alert_enabled=alert_enabled
                )
                created += 1
            except Exception:
                skipped += 1

        return {"created": created, "skipped": skipped}


class DashboardDataPattern:
    """Pattern for collecting dashboard data efficiently."""

    @staticmethod
    def get_dashboard_overview() -> Dict[str, Any]:
        """Get complete dashboard overview.

        Returns:
            Dictionary with all dashboard metrics.
        """
        return {
            "device_stats": {
                "total_active": HardwareService.count_active_receivers(),
                "online": HardwareService.count_online_receivers(),
                "offline": HardwareService.count_offline_receivers(),
                "low_battery": len(HardwareService.get_low_battery_receivers()),
            },
            "connection_health": {
                "unhealthy_connections": len(ConnectionHealthService.get_unhealthy_connections()),
                "total_errors": ConnectionHealthService.get_total_connection_errors(),
            },
            "assignments": {
                "total": AssignmentService.count_total_assignments(),
                "with_alerts": AssignmentService.count_assignments_with_alerts(),
            },
            "locations": {
                "total": LocationService.count_total_locations(),
                "with_devices": LocationService.count_locations_with_devices(),
            },
        }

    @staticmethod
    def get_user_dashboard(*, user: User) -> Dict[str, Any]:
        """Get user-specific dashboard data.

        Args:
            user: User to get dashboard for.

        Returns:
            Dictionary with user's dashboard data.
        """
        user_assignments = AssignmentService.get_assignments_for_user(user_id=user.id)
        assigned_devices = [a.device for a in user_assignments]

        return {
            "assignments_count": user_assignments.count(),
            "devices": {
                "total": len(assigned_devices),
                "online": sum(1 for d in assigned_devices if getattr(d, "is_online", False)),
                "offline": sum(1 for d in assigned_devices if not getattr(d, "is_online", False)),
                "low_battery": 0,  # Battery tracking moved to WirelessUnit
            },
            "alert_settings": {
                "enabled": sum(1 for a in user_assignments if a.alert_enabled),
                "disabled": sum(1 for a in user_assignments if not a.alert_enabled),
            },
        }


class AlertingPattern:
    """Pattern for implementing alerting based on device status."""

    @staticmethod
    def check_alerts_needed() -> Dict[str, List[str]]:
        """Check which alerts need to be sent.

        Returns:
            Dictionary with alert types and affected devices.
        """
        alerts = {
            "low_battery": [],
            "offline": [],
            "unhealthy_connection": [],
        }

        # Check low battery devices
        low_battery = HardwareService.get_low_battery_receivers(threshold=20)
        alerts["low_battery"] = [d.name for d in low_battery]

        # Check offline devices
        offline = HardwareService.get_offline_receivers()
        alerts["offline"] = [d.name for d in offline]

        # Check unhealthy connections
        unhealthy = ConnectionHealthService.get_unhealthy_connections()
        alerts["unhealthy_connection"] = [c.get("manufacturer_code") for c in unhealthy]

        return alerts

    @staticmethod
    def get_alerts_for_user(*, user: User) -> Dict[str, List[str]]:
        """Get alerts for user's assigned devices.

        Args:
            user: User to get alerts for.

        Returns:
            Dictionary with alert types and affected devices.
        """
        alerts = {
            "low_battery": [],
            "offline": [],
        }

        user_assignments = AssignmentService.get_assignments_for_user(user_id=user.id)

        for assignment in user_assignments:
            if not assignment.alert_on_hardware_offline:
                continue

            chassis = assignment.channel.chassis

            # Check low battery (active transmitter on the channel)
            if assignment.channel.active_wireless_unit:
                unit = assignment.channel.active_wireless_unit
                tx_battery = unit.battery_percentage
                if tx_battery and tx_battery < 20:
                    alerts["low_battery"].append(unit.name or f"Transmitter {unit.id}")

            # Check offline
            if not chassis.is_online:
                alerts["offline"].append(chassis.name or f"Chassis {chassis.id}")

        return alerts


class LocationManagementPattern:
    """Pattern for managing locations and device assignments."""

    @staticmethod
    def reorganize_devices_by_location(*, location_mappings: Dict[str, int]) -> Dict[str, int]:
        """Reorganize devices into locations.

        Args:
            location_mappings: Mapping of device names to location IDs.

        Returns:
            Statistics on reorganization.
        """
        success = 0
        failed = 0

        for device_name, location_id in location_mappings.items():
            try:
                device = HardwareService.get_device_by_name(name=device_name)
                location = LocationService.get_location_by_id(location_id=location_id)

                LocationService.assign_device_to_location(device_obj=device, location_obj=location)
                success += 1
            except Exception:
                failed += 1

        return {"success": success, "failed": failed}

    @staticmethod
    def get_location_summary(*, location_id: int) -> Dict[str, Any]:
        """Get complete summary for a location.

        Args:
            location_id: Location ID.

        Returns:
            Complete location information.
        """
        location = LocationService.get_location_by_id(location_id=location_id)
        devices = HardwareService.get_receivers_by_location(location_id=location_id)

        return {
            "name": location.name,
            "description": location.description,
            "device_count": devices.count(),
            "online_count": devices.filter(is_online=True).count(),
            "offline_count": devices.filter(is_online=False).count(),
            "low_battery_count": 0,  # Battery tracking moved to WirelessUnit
        }


class DiscoveryAndSyncPattern:
    """Pattern for discovering and syncing devices."""

    @staticmethod
    def full_sync_cycle() -> Dict[str, Any]:
        """Execute full sync cycle for all manufacturers.

        Returns:
            Sync statistics.
        """
        results = {
            "manufacturers": [],
            "total_synced": 0,
            "total_failed": 0,
        }

        manufacturers = ["shure", "sennheiser"]  # Add others as needed

        for code in manufacturers:
            try:
                result = ManufacturerService.sync_devices_for_manufacturer(manufacturer_code=code)

                synced = result.get("devices_synced", 0)
                results["manufacturers"].append(
                    {"code": code, "synced": synced, "status": "success"}
                )
                results["total_synced"] += synced

            except Exception as e:
                results["manufacturers"].append({"code": code, "error": str(e), "status": "failed"})
                results["total_failed"] += 1

        return results

    @staticmethod
    def discover_and_sync_new_devices(
        *, manufacturer_code: str, discovery_type: str = "cidr"
    ) -> Dict[str, Any]:
        """Discover and sync new devices for manufacturer.

        Args:
            manufacturer_code: Manufacturer code.
            discovery_type: Type of discovery ('cidr', 'mdns', etc.).

        Returns:
            Discovery and sync results.
        """
        # Run discovery
        discovery_result = DiscoveryService.run_discovery(
            discovery_type=discovery_type, manufacturer_code=manufacturer_code
        )

        # Sync discovered devices
        sync_result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer_code
        )

        return {
            "discovered": discovery_result.get("devices_found", 0),
            "synced": sync_result.get("devices_synced", 0),
        }


class ReportingPattern:
    """Pattern for generating reports."""

    @staticmethod
    def generate_device_status_report() -> str:
        """Generate device status report.

        Returns:
            Formatted report string.
        """
        report = "# Device Status Report\n\n"

        active_receivers = HardwareService.get_active_receivers()

        # Summary
        report += "## Summary\n"
        report += f"Total Receivers: {active_receivers.count()}\n"
        report += f"Online: {active_receivers.filter(is_online=True).count()}\n"
        report += f"Offline: {active_receivers.filter(is_online=False).count()}\n\n"

        # Low Battery
        # WirelessChassis doesn't have battery_level anymore, it's on WirelessUnit
        from micboard.models import WirelessUnit

        low_battery_units = WirelessUnit.objects.low_battery(threshold=20)
        if low_battery_units.count() > 0:
            report += "## Low Battery Devices\n"
            for unit in low_battery_units:
                report += (
                    f"- {unit.name} (on {unit.base_chassis.name}): {unit.battery_percentage}%\n"
                )
            report += "\n"

        # Offline Devices
        offline = active_receivers.filter(is_online=False)
        if offline.count() > 0:
            report += "## Offline Devices\n"
            for device in offline:
                last_seen = device.last_seen or "Never"
                report += f"- {device.name} (Last seen: {last_seen})\n"
            report += "\n"

        return report

    @staticmethod
    def generate_health_report() -> str:
        """Generate system health report.

        Returns:
            Formatted report string.
        """
        report = "# System Health Report\n\n"

        # Connection Health
        unhealthy = ConnectionHealthService.get_unhealthy_connections()

        report += "## Connection Health\n"
        if not unhealthy:
            report += "✓ All manufacturer connections are healthy\n"
        else:
            report += f"✗ {len(unhealthy)} unhealthy connections:\n"
            for conn in unhealthy:
                report += f"  - {conn.get('manufacturer_code')}\n"

        report += "\n"

        # Assignment Coverage
        report += "## Assignment Coverage\n"
        total_assignments = AssignmentService.count_total_assignments()
        report += f"Total Assignments: {total_assignments}\n"

        alerts_enabled = AssignmentService.count_assignments_with_alerts()
        report += f"Alerts Enabled: {alerts_enabled}\n\n"

        return report
