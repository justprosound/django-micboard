"""Fresh manufacturer activation checks for queued and long-lived work."""

from __future__ import annotations

from micboard.models.discovery.manufacturer import Manufacturer


class ManufacturerActivationService:
    """Read current activation state at external-work boundaries."""

    @staticmethod
    def is_active(manufacturer_id: int) -> bool:
        """Return whether the manufacturer still exists and permits outbound work."""
        return Manufacturer.objects.filter(pk=manufacturer_id, is_active=True).exists()
