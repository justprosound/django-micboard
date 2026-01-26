# file: micboard/models/locations/__init__.py
"""Location hierarchy models for physical device placement tracking.

Provides three-tier location structure: Building > Room > Location.
"""

from .structure import Building, Location, Room

__all__ = [
    "Building",
    "Room",
    "Location",
]
