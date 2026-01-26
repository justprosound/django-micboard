"""Discovery service layer for device discovery via CIDR and manual registration.

Handles device discovery operations and device registration workflows.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from micboard.models import Discovery, Manufacturer, WirelessChassis, WirelessUnit


class DiscoveryService:
    """Business logic for device discovery and registration."""

    @staticmethod
    def create_discovery_task(
        *, name: str, discovery_type: str, target: str, enabled: bool = True
    ) -> Discovery:
        """Create a new discovery task.

        Args:
            name: Task name.
            discovery_type: Type of discovery ('cidr', 'mdns', 'manual', etc.).
            target: Discovery target (e.g., CIDR range, hostname).
            enabled: Whether task is enabled.

        Returns:
            Created Discovery object.
        """
        return Discovery.objects.create(
            name=name, discovery_type=discovery_type, target=target, enabled=enabled
        )

    @staticmethod
    def get_enabled_discovery_tasks() -> QuerySet:
        """Get all enabled discovery tasks.

        Returns:
            QuerySet of enabled Discovery objects.
        """
        return Discovery.objects.filter(enabled=True)

    @staticmethod
    def update_discovery_task(
        *, task: Discovery, enabled: bool | None = None, target: str | None = None
    ) -> Discovery:
        """Update a discovery task.

        Args:
            task: Discovery instance.
            enabled: New enabled status, or None to skip.
            target: New target, or None to skip.

        Returns:
            Updated Discovery object.
        """
        updated = False
        if enabled is not None and task.enabled != enabled:
            task.enabled = enabled
            updated = True
        if target is not None and task.target != target:
            task.target = target
            updated = True

        if updated:
            task.save()

        return task

    @staticmethod
    def execute_discovery(*, task: Discovery) -> dict[str, Any]:
        """Execute a discovery task.

        This method would typically orchestrate the actual discovery logic.
        Currently returns a template for discovery results.

        Args:
            task: Discovery instance to execute.

        Returns:
            Dictionary with discovery results:
            {
                'success': bool,
                'devices_found': int,
                'devices_added': int,
                'devices_updated': int,
                'errors': list[str]
            }
        """
        # Placeholder for discovery execution logic
        # This should be implemented based on discovery_type
        return {
            "success": True,
            "devices_found": 0,
            "devices_added": 0,
            "devices_updated": 0,
            "errors": [],
        }

    @staticmethod
    def register_discovered_device(
        *, ip_address: str, device_type: str, name: str | None = None, manufacturer_code: str = ""
    ) -> WirelessChassis | WirelessUnit | None:
        """Register a newly discovered device.

        Args:
            ip_address: Device IP address.
            device_type: Device type ('receiver' or 'transmitter').
            name: Optional device name.
            manufacturer_code: Manufacturer code.

        Returns:
            Created device object or None if registration failed.
        """
        manufacturer = Manufacturer.objects.filter(code=manufacturer_code).first()

        if device_type == "receiver":
            return WirelessChassis.objects.create(
                ip=ip_address,
                name=name or ip_address,
                manufacturer=manufacturer,
                status="online",
                is_online=True,
                api_device_id=f"manual-{ip_address}",
            )
        elif device_type == "transmitter":
            # Transmitters strictly need a base chassis now
            # This legacy registration path is likely broken or needs update
            return None

        return None

    @staticmethod
    def get_discovery_results(*, task: Discovery) -> QuerySet:
        """Get devices discovered by a task.

        Args:
            task: Discovery instance.

        Returns:
            QuerySet of discovered devices.
        """
        return WirelessChassis.objects.none()

    @staticmethod
    def get_undiscovered_devices() -> QuerySet:
        """Get devices not yet discovered via automatic discovery.

        Returns:
            QuerySet of active chassis.
        """
        return WirelessChassis.objects.active()

    @staticmethod
    def run_discovery(*, task: Discovery) -> dict[str, Any]:
        """Run discovery for a task (alias for execute_discovery)."""
        return DiscoveryService.execute_discovery(task=task)
