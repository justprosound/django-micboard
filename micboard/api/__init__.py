"""Public API package for micboard.

This package re-exports the v1 API view classes for convenience. Tests
verify module docstrings exist for quality checks.
"""

from .v1.views.config_views import ConfigAPIView, GroupUpdateAPIView
from .v1.views.data_views import DataAPIView
from .v1.views.device_views import (
    DeviceDetailAPIView,
    ReceiverDetailAPIView,
    ReceiverListAPIView,
)
from .v1.views.discovery_views import AddDiscoveryIPsAPIView
from .v1.views.health_views import HealthCheckAPIView, ReadinessCheckAPIView
from .v1.views.other_views import (
    APIDocumentationAPIView,
    RefreshAPIView,
    UserAssignmentViewSet,
)
