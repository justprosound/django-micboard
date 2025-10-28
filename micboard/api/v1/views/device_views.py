import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.api.base_views import ManufacturerFilterMixin
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


class ReceiverListAPIView(ManufacturerFilterMixin, APIView):
    """
    API endpoint for listing receivers with summary information.
    Replaces micboard.api.core_views.api_receivers_list.
    """

    def get(self, request, *args, **kwargs):
        receivers_queryset = Receiver.objects.all().order_by("name")
        receivers_queryset, error_response = self.filter_queryset_by_manufacturer(
            receivers_queryset, request
        )
        if error_response:
            return error_response

        serializer = ReceiverSummarySerializer(receivers_queryset, many=True)
        return Response({"receivers": serializer.data, "count": len(serializer.data)})


class ReceiverDetailAPIView(ManufacturerFilterMixin, APIView):
    """
    API endpoint for detailed information of a specific receiver.
    Replaces micboard.api.core_views.api_receiver_detail.
    """

    def get(self, request, receiver_id, *args, **kwargs):
        receiver_queryset = Receiver.objects.prefetch_related("channels__transmitter")
        receiver_queryset, error_response = self.filter_queryset_by_manufacturer(
            receiver_queryset, request
        )
        if error_response:
            return error_response

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
