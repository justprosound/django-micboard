"""System health checks for django-micboard.

Integrates with django-health-check if installed.
"""

from __future__ import annotations

import dataclasses
import logging

from micboard.utils.dependencies import HAS_HEALTH_CHECK

logger = logging.getLogger(__name__)

if HAS_HEALTH_CHECK:
    from health_check.base import HealthCheck
    from health_check.exceptions import ServiceUnavailable

    @dataclasses.dataclass
    class ManufacturerConnectivityCheck(HealthCheck):
        """Check if manufacturer APIs are reachable."""

        def run(self) -> None:
            """Perform connectivity check for all active manufacturers."""
            from micboard.models.discovery.manufacturer import Manufacturer

            active_manufacturers = Manufacturer.objects.filter(is_active=True)
            if not active_manufacturers.exists():
                return

            for manufacturer in active_manufacturers:
                try:
                    plugin_class = manufacturer.get_plugin_class()
                    plugin = plugin_class(manufacturer)
                    if hasattr(plugin, "check_health"):
                        if not plugin.check_health():
                            raise ServiceUnavailable(
                                f"Manufacturer {manufacturer.name} health check failed"
                            )
                except Exception as e:
                    raise ServiceUnavailable(
                        f"Could not connect to {manufacturer.name}: {str(e)}"
                    ) from e


def check_micboard_configuration(app_configs, **kwargs):
    """Django system check for Micboard configuration."""
    errors = []
    # Add custom validation logic here if needed
    return errors
