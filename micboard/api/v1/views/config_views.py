import logging

from django.db import models
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.api.utils import _get_manufacturer_code
from micboard.models import (
    Group,
    Manufacturer,
    MicboardConfig,
)

logger = logging.getLogger(__name__)


class ConfigAPIView(APIView):
    """
    API endpoint to handle application configuration.
    Replaces micboard.api.core_views.ConfigHandler.
    """

    def get(self, request, *args, **kwargs):
        manufacturer_code = _get_manufacturer_code(request)

        config_queryset = MicboardConfig.objects.all()

        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                config_queryset = config_queryset.filter(
                    models.Q(manufacturer=manufacturer) | models.Q(manufacturer__isnull=True)
                )
            except Manufacturer.DoesNotExist:
                return Response(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            config_queryset = config_queryset.filter(manufacturer__isnull=True)

        config_data = {conf.key: conf.value for conf in config_queryset}
        return Response(config_data)

    def post(self, request, *args, **kwargs):
        try:
            data = request.data  # DRF automatically parses JSON
            manufacturer_code = _get_manufacturer_code(request)

            manufacturer = None
            if manufacturer_code:
                try:
                    manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                except Manufacturer.DoesNotExist:
                    return Response(
                        {"error": f"Manufacturer '{manufacturer_code}' not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            for key, value in data.items():
                MicboardConfig.objects.update_or_create(
                    key=key, manufacturer=manufacturer, defaults={"value": str(value)}
                )

            return Response({"success": True}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Config update error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GroupUpdateAPIView(APIView):
    """
    API endpoint to handle group updates.
    Replaces micboard.api.core_views.GroupUpdateHandler.
    """

    def post(self, request, group_id, *args, **kwargs):
        try:
            data = request.data  # DRF automatically parses JSON
            group_num = group_id  # Use group_id from URL
            if group_num is not None:
                Group.objects.update_or_create(
                    group_number=group_num,
                    defaults={
                        "title": data.get("title", ""),
                        "slots": data.get("slots", []),  # This will need to be re-evaluated later
                        "hide_charts": data.get("hide_charts", False),
                    },
                )
            return Response({"success": True}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Group update error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
