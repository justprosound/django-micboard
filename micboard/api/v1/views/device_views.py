import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.api.utils import _get_manufacturer_code
from micboard.models import (
    Manufacturer,
    Receiver,
)
from micboard.serializers import (
    ReceiverDetailSerializer,
    ReceiverSummarySerializer,
)
from micboard.signals import device_detail_requested

logger = logging.getLogger(__name__)


class ReceiverListAPIView(APIView):
    """
    API endpoint for listing receivers with summary information.
    Replaces micboard.api.core_views.api_receivers_list.
    """

    def get(self, request, *args, **kwargs):
        manufacturer_code = _get_manufacturer_code(request)

        receivers_queryset = Receiver.objects.all().order_by("name")
        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                receivers_queryset = receivers_queryset.filter(manufacturer=manufacturer)
            except Manufacturer.DoesNotExist:
                return Response(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        serializer = ReceiverSummarySerializer(receivers_queryset, many=True)
        return Response({"receivers": serializer.data, "count": len(serializer.data)})


class ReceiverDetailAPIView(APIView):
    """
    API endpoint for detailed information of a specific receiver.
    Replaces micboard.api.core_views.api_receiver_detail.
    """

    def get(self, request, receiver_id, *args, **kwargs):
        manufacturer_code = _get_manufacturer_code(request)

        receiver_queryset = Receiver.objects.prefetch_related("channels__transmitter")
        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                receiver_queryset = receiver_queryset.filter(manufacturer=manufacturer)
            except Manufacturer.DoesNotExist:
                return Response(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            receiver = receiver_queryset.get(api_device_id=receiver_id)
        except Receiver.DoesNotExist:
            return Response({"error": "Receiver not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = ReceiverDetailSerializer(receiver)
        return Response(serializer.data)


class DeviceDetailAPIView(APIView):
    """
    API endpoint for on-demand fetching of a device's current data from the manufacturer API.
    Replaces micboard.api.core_views.api_device_detail.
    """

    def get(self, request, device_id, *args, **kwargs):
        manufacturer_code = _get_manufacturer_code(request)
        try:
            responses = device_detail_requested.send_robust(
                sender=self.__class__,
                manufacturer=manufacturer_code,
                device_id=device_id,
                request=request,
            )
            for _, resp in responses:
                if isinstance(resp, dict):
                    return Response({"success": True, "result": resp})
            return Response({"error": "No data found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception("Error fetching device detail: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
