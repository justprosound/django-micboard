"""Common integration patterns and helpers for django-micboard services.

Provides ready-to-use patterns for common use cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, cast

from micboard.services import (
    ConnectionHealthService,
    HardwareService,
    LocationService,
    ManufacturerService,
    PerformerAssignmentService,
)

# DiscoveryService lives in a dedicated module; import explicitly to satisfy mypy
from micboard.services.discovery_service_new import DiscoveryService

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.db.models import QuerySet

    from micboard.models import PerformerAssignment, WirelessChassis, WirelessUnit


class BulkOperationPattern:
    """Pattern for bulk operations using services."""

    @staticmethod
    def bulk_sync_device_status(
        *, devices: list[WirelessChassis | WirelessUnit], online: bool
    ) -> dict[str, int]:
        # Prefer HardwareService.sync_hardware_status signature (obj, online)
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
                # HardwareService.sync_hardware_status uses (obj, online)
                HardwareService.sync_hardware_status(obj=device, online=online)
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
            channel = cast(Any, receiver).rf_channels.first()
            if channel is None:
                skipped += 1
                continue

            try:
                # Bulk creation requires business-specific mapping from user -> performer
                # This helper cannot create assignments without a performer reference; skip.
                logger = __import__("logging").getLogger(__name__)
                logger.warning(
                    "Skipping bulk assignment for channel %s: no performer mapping available",
                    channel.id,
                )
                skipped += 1
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
                # total_active: sum of chassis + field units
                "total_active": (
                    HardwareService.get_active_chassis().count()
                    + HardwareService.get_active_units().count()
                ),
                "online": (
                    HardwareService.count_online_hardware().get("chassis", 0)
                    + HardwareService.count_online_hardware().get("units", 0)
                ),
                "offline": (
                    (
                        HardwareService.get_active_chassis().count()
                        + HardwareService.get_active_units().count()
                    )
                    - (
                        HardwareService.count_online_hardware().get("chassis", 0)
                        + HardwareService.count_online_hardware().get("units", 0)
                    )
                ),
                "low_battery": cast(
                    int, cast(Any, WirelessUnit.objects).low_battery(threshold=20).count()
                ),
            },
            "connection_health": {
                "unhealthy_connections": len(ConnectionHealthService.get_unhealthy_connections()),
                "total_errors": cast(
                    Dict[str, Any], ConnectionHealthService.get_connection_stats()
                ).get("error_connections", 0),
            },
            "assignments": {
                "total": (
                    __import__("micboard.models")
                    .models.performer_assignment.PerformerAssignment.objects.active()
                    .count()
                ),
                "with_alerts": (
                    __import__("micboard.models")
                    .models.performer_assignment.PerformerAssignment.objects.needing_alerts()
                    .count()
                ),
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
        # Interpreting "get_assignments_for_user" as assignments the user created (assigned_by)
        user_assignments = (
            PerformerAssignmentService.get_active_assignments()
            .filter(assigned_by=user)
            .select_related(
                "performer",
                "wireless_unit",
                "wireless_unit__base_chassis",
            )
        )
        assignments_list = cast(List["PerformerAssignment"], list(user_assignments))
        assigned_devices: List["WirelessUnit"] = [
            a.wireless_unit
            for a in assignments_list
            if getattr(a, "wireless_unit", None) is not None
        ]

        enabled_alerts = [
            a
            for a in assignments_list
            if getattr(a, "alert_on_battery_low", False)
            or getattr(a, "alert_on_signal_loss", False)
            or getattr(a, "alert_on_hardware_offline", False)
        ]

        return {
            "assignments_count": len(assignments_list),
            "devices": {
                "total": len(assigned_devices),
                "online": len(
                    [d for d in assigned_devices if getattr(d, "status", "") == "online"]
                ),
                "offline": len(
                    [d for d in assigned_devices if getattr(d, "status", "") != "online"]
                ),
                "low_battery": 0,  # Battery tracking moved to WirelessUnit
            },
            "alert_settings": {
                "enabled": len(enabled_alerts),
                "disabled": max(0, len(assignments_list) - len(enabled_alerts)),
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
        alerts: Dict[str, List[str]] = {
            "low_battery": [],
            "offline": [],
            "unhealthy_connection": [],
        }

        # Check low battery devices
        low_battery = cast(
            "QuerySet[WirelessUnit]", cast(Any, WirelessUnit.objects).low_battery(threshold=20)
        )
        alerts["low_battery"] = [cast("WirelessUnit", d).name for d in low_battery]

        # Check offline devices
        offline = HardwareService.get_active_chassis().filter(is_online=False)
        alerts["offline"] = [d.name for d in offline]

        # Check unhealthy connections
        unhealthy = cast(List[Dict[str, Any]], ConnectionHealthService.get_unhealthy_connections())
        alerts["unhealthy_connection"] = [
            str(c.get("manufacturer_code"))
            for c in unhealthy
            if c.get("manufacturer_code") is not None
        ]

        return alerts

    @staticmethod
    def get_alerts_for_user(*, user: User) -> Dict[str, List[str]]:
        """Get alerts for user's assigned devices.

        Args:
            user: User to get alerts for.

        Returns:
            Dictionary with alert types and affected devices.
        """
        alerts: Dict[str, List[str]] = {
            "low_battery": [],
            "offline": [],
        }

        # Use performer assignments created by this user as a heuristic
        user_assignments = (
            PerformerAssignmentService.get_active_assignments()
            .filter(assigned_by=user)
            .select_related(
                "wireless_unit",
                "wireless_unit__base_chassis",
            )
        )

        assignments_list = cast(List["PerformerAssignment"], list(user_assignments))
        for assignment in assignments_list:
            assignment = cast("PerformerAssignment", assignment)
            if not getattr(assignment, "alert_on_hardware_offline", False):
                continue

            chassis = getattr(assignment.wireless_unit, "base_chassis", None)

            # Check low battery (active transmitter on the unit)
            unit = getattr(assignment, "wireless_unit", None)
            if unit:
                unit = cast("WirelessUnit", unit)
                tx_battery = getattr(unit, "battery", None)
                if tx_battery is not None and tx_battery < 20:
                    alerts["low_battery"].append(
                        unit.name or f"Transmitter {getattr(unit, 'id', 'unknown')}"
                    )

            # Check offline
            if chassis and not getattr(chassis, "is_online", False):
                alerts["offline"].append(
                    getattr(chassis, "name", f"Chassis {getattr(chassis, 'id', 'unknown')}")
                )

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
                # Prefer search_hardware which returns matching chassis/units; pick the first match
                matches = HardwareService.search_hardware(query=device_name)
                device = matches[0] if matches else None
                location = LocationService.get_location_by_id(location_id=location_id)

                if not location or not device:
                    failed += 1
                    continue

                # device may be WirelessChassis or WirelessUnit; normalize to a chassis for assignment
                device_to_assign = getattr(device, "base_chassis", device)
                device_to_assign = cast("WirelessChassis", device_to_assign)

                try:
                    LocationService.assign_device_to_location(
                        device=device_to_assign, location=location
                    )
                    success += 1
                except Exception:
                    failed += 1
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
        devices = HardwareService.get_active_chassis().filter(location_id=location_id)

        if location is None:
            return {
                "name": "Unknown",
                "description": "",
                "device_count": 0,
                "online_count": 0,
                "offline_count": 0,
                "low_battery_count": 0,
            }

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
        manufacturers_results: List[Dict[str, Any]] = []
        total_synced = 0
        total_failed = 0

        manufacturers = ["shure", "sennheiser"]  # Add others as needed

        for code in manufacturers:
            try:
                result = ManufacturerService.sync_devices_for_manufacturer(manufacturer_code=code)

                synced = result.get("devices_synced", 0)
                manufacturers_results.append({"code": code, "synced": synced, "status": "success"})
                total_synced += synced

            except Exception as e:
                manufacturers_results.append({"code": code, "error": str(e), "status": "failed"})
                total_failed += 1

        return {
            "manufacturers": manufacturers_results,
            "total_synced": total_synced,
            "total_failed": total_failed,
        }

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
        # Run discovery for the specific manufacturer
        from micboard.models import Manufacturer

        manufacturer = Manufacturer.objects.filter(code=manufacturer_code).first()
        discovered = 0
        if manufacturer:
            DiscoveryService()._run_manufacturer_discovery(
                manufacturer=manufacturer,
                scan_cidrs=(discovery_type == "cidr"),
                scan_fqdns=(discovery_type == "fqdn"),
                max_hosts=1024,
            )
            # DiscoveryService currently does not return counts; set to 0 as placeholder.
            discovered = 0

        # Sync discovered devices
        sync_result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer_code
        )

        return {
            "discovered": discovered,
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

        # Use active chassis as 'receivers' for report purposes
        active_receivers = HardwareService.get_active_chassis()

        # Summary
        report += "## Summary\n"
        report += f"Total Receivers: {active_receivers.count()}\n"
        report += f"Online: {active_receivers.filter(is_online=True).count()}\n"
        report += f"Offline: {active_receivers.filter(is_online=False).count()}\n\n"

        # Low Battery
        # WirelessChassis doesn't have battery_level anymore, it's on WirelessUnit
        from micboard.models import WirelessUnit

        low_battery_units = cast(
            "QuerySet[WirelessUnit]", cast(Any, WirelessUnit.objects).low_battery(threshold=20)
        )
        if low_battery_units.count() > 0:
            report += "## Low Battery Devices\n"
            for unit in low_battery_units:
                unit = cast("WirelessUnit", unit)
                report += (
                    f"- {unit.name} (on {unit.base_chassis.name}): {unit.battery_percentage}%\n"
                )
            report += "\n"

        # Offline Devices
        offline = active_receivers.filter(is_online=False)
        if offline.count() > 0:
            report += "## Offline Devices\n"
            for device in offline:
                device = cast("WirelessChassis", device)
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
        report += "## Connection Health\n"
        unhealthy = cast(List[Dict[str, Any]], ConnectionHealthService.get_unhealthy_connections())
        if not unhealthy:
            report += "✓ All manufacturer connections are healthy\n"
        else:
            report += f"✗ {len(unhealthy)} unhealthy connections:\n"
            for conn in unhealthy:
                report += f"  - {conn.get('manufacturer_code')}\n"

        report += "\n"

        # Assignment Coverage
        report += "## Assignment Coverage\n"
        # Assignment statistics (use PerformerAssignment queries)
        from micboard.models import PerformerAssignment

        total_assignments = cast(int, cast(Any, PerformerAssignment.objects).active().count())
        report += f"Total Assignments: {total_assignments}\n"

        alerts_enabled = cast(int, cast(Any, PerformerAssignment.objects).needing_alerts().count())
        report += f"Alerts Enabled: {alerts_enabled}\n\n"

        return report
