import logging

from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.decorators import rate_limit_view
from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


@method_decorator(rate_limit_view(max_requests=120, window_seconds=60), name="dispatch")
class AddDiscoveryIPsAPIView(APIView):
    """Accept a JSON body with an `ips` list and an optional `manufacturer` code.

    Body example: {"ips": ["192.168.1.10", "192.168.1.11"], "manufacturer": "shure"}
    If `manufacturer` is omitted from the body, the view will try to read it from
    the `?manufacturer=` query parameter.
    """

    def post(self, request, *args, **kwargs):
        # Support both DRF Request (request.data) and plain Django HttpRequest
        # Prefer DRF parsed data if available. Only fallback to parsing raw
        # body when the request object does not expose a .data attribute.
        data = None
        if hasattr(request, "data"):
            try:
                data = request.data
            except Exception:
                data = None

        if data is None:
            # Fallback: parse raw JSON body if present (Django HttpRequest)
            try:
                import json as _json

                raw = getattr(request, "body", None)
                if raw:
                    data = _json.loads(raw.decode("utf-8"))
                else:
                    data = {}
            except Exception:
                data = {}
        # parsed data is in `data`
        ips = data.get("ips")
        manufacturer_code = data.get("manufacturer") or request.GET.get("manufacturer")

        if not ips or not isinstance(ips, (list, tuple)):
            return Response(
                {"success": False, "error": "Provide a non-empty 'ips' list in request body"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not manufacturer_code:
            return Response(
                {"success": False, "error": "Manufacturer code required (body or ?manufacturer=)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            return Response(
                {"success": False, "error": f"Manufacturer '{manufacturer_code}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            plugin_cls = get_manufacturer_plugin(manufacturer.code)
            plugin = plugin_cls(manufacturer)
        except Exception as exc:
            logger.exception("Failed to initialize plugin for %s: %s", manufacturer.code, exc)
            return Response(
                {"success": False, "error": "Failed to initialize manufacturer plugin"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Try to obtain a client that implements add_discovery_ips
        client = None

        try:
            client = plugin.get_client()
        except Exception:
            client = getattr(plugin, "client", None)

        if client is None or not hasattr(client, "add_discovery_ips"):
            return Response(
                {
                    "success": False,
                    "error": "Manufacturer plugin does not support discovery operations",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            accepted = client.add_discovery_ips(list(ips))
        except Exception as exc:
            logger.exception("Error adding discovery IPs for %s: %s", manufacturer.code, exc)
            return Response(
                {"success": False, "error": "Failed to add discovery IPs"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if accepted:
            return Response({"success": True, "message": "Discovery IPs submitted"})
        else:
            return Response(
                {"success": False, "error": "API rejected discovery IPs or operation failed"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
