"""System health checks for django-micboard.

Integrates with django-health-check if installed.
"""

from __future__ import annotations

import logging

from micboard.models import Manufacturer
from micboard.utils.dependencies import HAS_HEALTH_CHECK

logger = logging.getLogger(__name__)

if HAS_HEALTH_CHECK:
    from health_check.backends import BaseHealthCheckBackend
    from health_check.plugins import plugin_dir

    class ManufacturerConnectivityCheck(BaseHealthCheckBackend):
        """Check if manufacturer APIs are reachable."""

        def check_status(self):
            """Perform connectivity check for all active manufacturers."""
            active_manufacturers = Manufacturer.objects.filter(is_active=True)
            if not active_manufacturers.exists():
                return

            for manufacturer in active_manufacturers:
                try:
                    plugin_class = manufacturer.get_plugin_class()
                    plugin = plugin_class(manufacturer)
                    if hasattr(plugin, "check_health"):
                        if not plugin.check_health():
                            self.add_error(f"Manufacturer {manufacturer.name} health check failed")
                except Exception as e:
                    self.add_error(f"Could not connect to {manufacturer.name}: {str(e)}")

    # Register the check
    plugin_dir.register(ManufacturerConnectivityCheck)


def check_micboard_configuration(app_configs, **kwargs):
    """Django system check for Micboard configuration."""
    errors = []
    # Add custom validation logic here if needed
    return errors
