"""Sennheiser manufacturer plugin package for django-micboard.

This package exposes the SennheiserPlugin implementation used by the
micboard manufacturers plugin system.
"""

from .plugin import SennheiserPlugin

__all__ = ["SennheiserPlugin"]
