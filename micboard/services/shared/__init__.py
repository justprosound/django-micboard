"""Shared utilities and infrastructure for django-micboard services.

This package contains:
- Common utilities (pagination, filtering, search)
- Service exceptions
- Generic CRUD operations
- Multi-tenant filtering
- Settings registry
- Compliance and validation utilities
"""

from __future__ import annotations

from .base_crud import GenericCRUDService
from .compliance import ComplianceResult, ComplianceService
from .exceptions import (
    ConnectionError,
    DiscoveryError,
    HardwareNotFoundError,
    LocationAlreadyExistsError,
    LocationNotFoundError,
    ManufacturerPluginError,
    MicboardServiceError,
)
from .pagination import PaginatedResult, filter_by_search, paginate_queryset
from .settings_registry import SettingNotFoundError, SettingsRegistry
from .sync_utils import SyncResult
from .tenant_filters import apply_tenant_filters

__all__ = [
    "ComplianceResult",
    "ComplianceService",
    "ConnectionError",
    "DiscoveryError",
    "GenericCRUDService",
    "HardwareNotFoundError",
    "LocationAlreadyExistsError",
    "LocationNotFoundError",
    "ManufacturerPluginError",
    "MicboardServiceError",
    "PaginatedResult",
    "SettingNotFoundError",
    "SettingsRegistry",
    "SyncResult",
    "apply_tenant_filters",
    "filter_by_search",
    "paginate_queryset",
]
