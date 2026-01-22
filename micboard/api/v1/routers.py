"""
API router configuration for DRF endpoints.

Registers all viewsets and generates API documentation.
"""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from micboard.api.v1.viewsets import (
    ChannelViewSet,
    GroupViewSet,
    LocationViewSet,
    ManufacturerConfigurationViewSet,
    ManufacturerViewSet,
    ReceiverViewSet,
    RoomViewSet,
    ServiceHealthViewSet,
    TransmitterViewSet,
)

router = DefaultRouter()

# Core model endpoints
router.register(r"manufacturers", ManufacturerViewSet, basename="manufacturer")
router.register(r"receivers", ReceiverViewSet, basename="receiver")
router.register(r"transmitters", TransmitterViewSet, basename="transmitter")
router.register(r"channels", ChannelViewSet, basename="channel")

# Organization endpoints
router.register(r"locations", LocationViewSet, basename="location")
router.register(r"rooms", RoomViewSet, basename="room")
router.register(r"groups", GroupViewSet, basename="group")

# Configuration endpoints
router.register(
    r"configurations",
    ManufacturerConfigurationViewSet,
    basename="configuration",
)

# Service health endpoints
router.register(r"health", ServiceHealthViewSet, basename="service-health")

urlpatterns = router.urls
