"""Kiosk/display wall views for stage and charger monitoring displays."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView

from micboard.models import DisplayWall, WallSection
from micboard.services.charger_assignment import ChargerAssignmentService
from micboard.services.connection_validation import ConnectionValidationService

logger = logging.getLogger(__name__)


class KioskAuthView(View):
    """Authenticate kiosk by ID (no user login required for remote displays)."""

    def get(self, request: HttpRequest, kiosk_id: str) -> HttpResponse:
        """Get kiosk display page by ID.

        Args:
            request: HTTP request
            kiosk_id: Kiosk identifier

        Returns:
            Kiosk display HTML or 404
        """
        wall = get_object_or_404(DisplayWall, kiosk_id=kiosk_id, is_active=True)

        # Update heartbeat
        from django.utils import timezone

        wall.last_heartbeat = timezone.now()
        wall.save(update_fields=["last_heartbeat"])

        # Get display data
        display_data = ChargerAssignmentService.get_display_wall_data(wall.id)

        context = {
            "wall": display_data.get("wall", {}),
            "sections": display_data.get("sections", []),
            "kiosk": True,
        }

        return render(request, "micboard/kiosk/display.html", context)

    def post(self, request: HttpRequest, kiosk_id: str) -> JsonResponse:
        """Heartbeat update from kiosk."""
        from django.utils import timezone

        try:
            wall = DisplayWall.objects.get(kiosk_id=kiosk_id, is_active=True)
            wall.last_heartbeat = timezone.now()
            wall.save(update_fields=["last_heartbeat"])
            return JsonResponse({"status": "ok", "message": "Heartbeat received"})
        except DisplayWall.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Kiosk not found"}, status=404)


@method_decorator(login_required, name="dispatch")
class DisplayWallListView(ListView):
    """List all display walls for administrator."""

    model = DisplayWall
    template_name = "micboard/kiosk/wall_list.html"
    context_object_name = "walls"
    paginate_by = 20

    def get_queryset(self):
        """Get display walls for user's location."""
        return DisplayWall.objects.filter(is_active=True).order_by("location__name", "name")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add health check data."""
        context = super().get_context_data(**kwargs)
        return context


@method_decorator(login_required, name="dispatch")
class DisplayWallDetailView(DetailView):
    """Show display wall details and health."""

    model = DisplayWall
    template_name = "micboard/kiosk/wall_detail.html"
    context_object_name = "wall"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add performance data and health checks."""
        context = super().get_context_data(**kwargs)
        wall = self.get_object()

        # Get display data
        display_data = ChargerAssignmentService.get_display_wall_data(wall.id)
        context["display_data"] = display_data

        # Get health checks for all chargers in sections
        charger_health = []
        for section in wall.sections.filter(is_active=True):
            for charger in section.chargers.all():
                health = ConnectionValidationService.check_charger_health(charger.id)
                charger_health.append(health)
        context["charger_health"] = charger_health

        # Kiosk URLs
        context["kiosk_url"] = f"/kiosk/{wall.kiosk_id}/"

        return context


@method_decorator(login_required, name="dispatch")
class WallSectionListView(ListView):
    """List wall sections for a display wall."""

    model = WallSection
    template_name = "micboard/kiosk/section_list.html"
    context_object_name = "sections"
    paginate_by = 50

    def get_queryset(self):
        """Get sections for specified wall."""
        wall_id = self.kwargs.get("wall_id")
        return WallSection.objects.filter(wall_id=wall_id, is_active=True).order_by("display_order")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add wall context."""
        context = super().get_context_data(**kwargs)
        wall_id = self.kwargs.get("wall_id")
        context["wall"] = get_object_or_404(DisplayWall, id=wall_id)
        return context


@method_decorator(login_required, name="dispatch")
class KioskDataView(View):
    """JSON API endpoint for kiosk real-time updates."""

    def get(self, request: HttpRequest, wall_id: int) -> JsonResponse:
        """Get current display data for a wall.

        Used by HTMX to refresh performer/charger data.

        Args:
            request: HTTP request
            wall_id: DisplayWall ID

        Returns:
            JSON with performer and charger data
        """
        try:
            wall = DisplayWall.objects.get(id=wall_id, is_active=True)
        except DisplayWall.DoesNotExist:
            return JsonResponse({"error": "Wall not found"}, status=404)

        display_data = ChargerAssignmentService.get_display_wall_data(wall.id)

        return JsonResponse(
            {
                "status": "ok",
                "wall": display_data.get("wall", {}),
                "sections": display_data.get("sections", []),
            }
        )


@method_decorator(login_required, name="dispatch")
class KioskHealthView(View):
    """JSON API endpoint for kiosk health status."""

    def get(self, request: HttpRequest, wall_id: int) -> JsonResponse:
        """Get health status for all chargers in wall sections.

        Args:
            request: HTTP request
            wall_id: DisplayWall ID

        Returns:
            JSON with health status for each charger
        """
        try:
            wall = DisplayWall.objects.prefetch_related("sections__chargers").get(
                id=wall_id, is_active=True
            )
        except DisplayWall.DoesNotExist:
            return JsonResponse({"error": "Wall not found"}, status=404)

        charger_health = []
        for section in wall.sections.filter(is_active=True):
            for charger in section.chargers.all():
                health = ConnectionValidationService.check_charger_health(charger.id)
                charger_health.append(health)

        return JsonResponse(
            {
                "status": "ok",
                "wall_id": wall.id,
                "chargers": charger_health,
            }
        )
