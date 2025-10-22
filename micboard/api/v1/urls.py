from django.urls import path
from rest_framework.routers import DefaultRouter

from .views.config_views import ConfigAPIView, GroupUpdateAPIView
from .views.data_views import DataAPIView
from .views.device_views import (
    DeviceDetailAPIView,
    ReceiverDetailAPIView,
    ReceiverListAPIView,
)
from .views.discovery_views import AddDiscoveryIPsAPIView
from .views.health_views import HealthCheckAPIView, ReadinessCheckAPIView
from .views.other_views import (
    APIDocumentationAPIView,
    RefreshAPIView,
    UserAssignmentViewSet,
)

router = DefaultRouter()
router.register(r"user-assignments", UserAssignmentViewSet, basename="user-assignment")

urlpatterns = [
    path("health/", HealthCheckAPIView.as_view(), name="health"),
    path("health/detailed/", HealthCheckAPIView.as_view(), name="health_detailed"),
    path("health/ready/", ReadinessCheckAPIView.as_view(), name="health_ready"),
    path("docs/", APIDocumentationAPIView.as_view(), name="docs"),
    path("data/", DataAPIView.as_view(), name="data"),
    path("receivers/", ReceiverListAPIView.as_view(), name="receivers_list"),
    path("receivers/<str:receiver_id>/", ReceiverDetailAPIView.as_view(), name="receiver_detail"),
    path("devices/<str:device_id>/", DeviceDetailAPIView.as_view(), name="device_detail"),
    path("discovery/ips/", AddDiscoveryIPsAPIView.as_view(), name="add_discovery_ips"),
    path("refresh/", RefreshAPIView.as_view(), name="refresh"),
    path("config/", ConfigAPIView.as_view(), name="config"),
    path("groups/<int:group_id>/", GroupUpdateAPIView.as_view(), name="group_update"),
]

urlpatterns += router.urls
