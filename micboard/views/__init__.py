"""
Views for the micboard app.
"""

from .api import (
    ConfigHandler,
    GroupUpdateHandler,
    api_discover,
    api_refresh,
    data_json,
)
from .dashboard import about, index

__all__ = [
    "ConfigHandler",
    "GroupUpdateHandler",
    "about",
    "api_discover",
    "api_refresh",
    "data_json",
    "index",
]
