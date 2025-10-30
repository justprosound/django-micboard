import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.api.base_views import ManufacturerFilterMixin
from micboard.models import Charger
from micboard.serializers import ChargerDetailSerializer, ChargerSummarySerializer

logger = logging.getLogger(__name__)


class ChargerListAPIView(ManufacturerFilterMixin, APIView):
    """
    API endpoint for listing chargers with summary information.
    """

    def get(self, request, *args, **kwargs):
        chargers_queryset = Charger.objects.all().order_by("name")
        chargers_queryset, error_response = self.filter_queryset_by_manufacturer(
            chargers_queryset, request
        )
        if error_response:
            return error_response

        serializer = ChargerSummarySerializer(chargers_queryset, many=True)
        return Response({"chargers": serializer.data, "count": len(serializer.data)})


class ChargerDetailAPIView(ManufacturerFilterMixin, APIView):
    """
    API endpoint for detailed information of a specific charger.
    """

    def get(self, request, charger_id, *args, **kwargs):
        charger_queryset = Charger.objects.prefetch_related("slots__transmitter")
        charger_queryset, error_response = self.filter_queryset_by_manufacturer(
            charger_queryset, request
        )
        if error_response:
            return error_response

        try:
            charger = charger_queryset.get(api_device_id=charger_id)
        except Charger.DoesNotExist:
            return Response({"error": "Charger not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = ChargerDetailSerializer(charger)
        return Response(serializer.data)
