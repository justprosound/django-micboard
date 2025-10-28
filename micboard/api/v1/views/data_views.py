from django.core.cache import cache
from django.db import models
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.api.base_views import ManufacturerFilterMixin
from micboard.models import (
    DiscoveredDevice,
    Group,
    MicboardConfig,
    Receiver,
)
from micboard.serializers import (
    DiscoveredDeviceSerializer,
    GroupSerializer,
    ReceiverSummarySerializer,
)


class DataAPIView(ManufacturerFilterMixin, APIView):
    """
    API endpoint for aggregated device data.
    Replaces micboard.api.core_views.data_json.
    """

    def get(self, request, *args, **kwargs):
        # Try to get fresh data from cache first (with manufacturer-specific cache key)
        manufacturer_code = request.GET.get("manufacturer")
        cache_key = f"micboard_device_data_{manufacturer_code or 'all'}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        # Serialize receivers
        receivers_queryset = (
            Receiver.objects.filter(is_active=True)
            .prefetch_related("channels__transmitter")
        )
        receivers_queryset, error_response = self.filter_queryset_by_manufacturer(
            receivers_queryset, request
        )
        if error_response:
            return error_response

        receivers_data = ReceiverSummarySerializer(receivers_queryset, many=True).data

        # Serialize discovered devices (filter by manufacturer if specified)
        discovered_queryset = DiscoveredDevice.objects.all()
        # TODO: Add proper filtering for discovered devices by manufacturer
        discovered_data = DiscoveredDeviceSerializer(discovered_queryset, many=True).data

        # Serialize config
        config_queryset = MicboardConfig.objects.all()
        if manufacturer_code:
            config_queryset = config_queryset.filter(
                models.Q(manufacturer__code=manufacturer_code) | models.Q(manufacturer__isnull=True)
            )
        else:
            config_queryset = config_queryset.filter(manufacturer__isnull=True)
        config_data = {conf.key: conf.value for conf in config_queryset}

        # Serialize groups
        groups_queryset = Group.objects.all()
        groups_data = GroupSerializer(groups_queryset, many=True).data

        data = {
            "receivers": receivers_data,
            "url": request.build_absolute_uri("/"),
            "gif": [],  # Placeholder for future media support
            "jpg": [],  # Placeholder for future media support
            "mp4": [],  # Placeholder for future media support
            "config": config_data,
            "discovered": discovered_data,
            "groups": groups_data,
        }

        # Cache for 30 seconds
        cache.set(cache_key, data, timeout=30)

        response = Response(data)
        # Provide renderer metadata so tests that call response.render() work
        try:
            response.accepted_renderer = JSONRenderer()
            response.accepted_media_type = "application/json"
            response.renderer_context = {"request": request}
        except Exception:
            # Best-effort: if setting renderer metadata fails, return response as-is
            pass

        return response
