"""Django Micboard - Wireless Hardware Monitoring System.

A community-driven open source Django app for monitoring wireless audio
hardware via manufacturer APIs. Provides real-time WebSocket updates, hardware
discovery, performer assignments, and alert management.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

__version__ = "26.01.27"  # CalVer: YY.MM.DD
__license__ = "AGPL-3.0-or-later"

# Modern Django automatically discovers AppConfig classes; no default_app_config needed

# Public API - convenience imports for common use cases
from micboard.apps import MicboardConfig


def __getattr__(name: str):
    """Lazy imports for public API to avoid circular dependencies."""
    if name == "models":
        from micboard import models

        return models
    elif name == "services":
        from micboard import services

        return services
    elif name == "get_config":
        return MicboardConfig.get_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    "__license__",
    "MicboardConfig",
    "get_config",
    "models",
    "services",
]
