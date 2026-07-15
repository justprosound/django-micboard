"""Kiosk/display wall views for stage and charger monitoring displays."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView

from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.services.kiosk.dtos import DisplayWallSnapshot
from micboard.services.kiosk.health_service import KioskHealthService
from micboard.services.kiosk.services import KioskService
from micboard.services.monitoring.monitoring_access import MonitoringService


@method_decorator(login_required, name="dispatch")
class KioskAuthView(View):
    """Display an active kiosk within the authenticated user's location scope."""

    def get(self, request: HttpRequest, kiosk_id: str) -> HttpResponse:
        """Get kiosk display page by ID.

        Args:
            request: HTTP request
            kiosk_id: Kiosk identifier

        Returns:
            Kiosk display HTML or 404
        """
        snapshot = KioskService.get_kiosk_snapshot(kiosk_id, user=request.user)
        if snapshot is None:
            raise Http404("Kiosk not found")
        return render(
            request,
            "micboard/kiosk/display.html",
            {"snapshot": snapshot, "kiosk": True},
        )

    def post(self, request: HttpRequest, kiosk_id: str) -> JsonResponse:
        """Heartbeat update from kiosk."""
        if KioskService.record_heartbeat(kiosk_id, user=request.user):
            return JsonResponse({"status": "ok", "message": "Heartbeat received"})
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
        return (
            MonitoringService.get_accessible_display_walls(self.request.user)
            .filter(is_active=True)
            .order_by("location__name", "name")
        )

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

    def get_queryset(self):
        """Limit wall lookup to the authenticated user's locations."""
        return MonitoringService.get_accessible_display_walls(self.request.user).filter(
            is_active=True
        )


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
        return (
            MonitoringService.get_accessible_wall_sections(self.request.user)
            .filter(
                wall_id=wall_id,
                is_active=True,
            )
            .order_by("display_order")
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add wall context."""
        context = super().get_context_data(**kwargs)
        wall_id = self.kwargs.get("wall_id")
        context["wall"] = get_object_or_404(
            MonitoringService.get_accessible_display_walls(self.request.user),
            id=wall_id,
        )
        return context


def _serialize_kiosk_data(snapshot: DisplayWallSnapshot) -> dict[str, Any]:
    """Adapt a typed snapshot to the stable programmatic kiosk response shape."""
    return {
        "wall": snapshot.wall.model_dump(mode="json"),
        "sections": [
            {
                "section": section.model_dump(mode="json", exclude={"performers"}),
                "performers": [group.model_dump(mode="json") for group in section.performers],
            }
            for section in snapshot.sections
        ],
    }


@method_decorator(login_required, name="dispatch")
class KioskDataView(View):
    """JSON snapshot endpoint for programmatic display consumers."""

    def get(self, request: HttpRequest, wall_id: int) -> JsonResponse:
        """Get current display data for a wall.

        Args:
            request: HTTP request
            wall_id: DisplayWall ID

        Returns:
            JSON with performer and charger data
        """
        snapshot = KioskService.get_wall_snapshot(wall_id, user=request.user)
        if snapshot is None:
            return JsonResponse({"error": "Wall not found"}, status=404)
        return JsonResponse({"status": "ok", **_serialize_kiosk_data(snapshot)})


@method_decorator(login_required, name="dispatch")
class KioskContentView(View):
    """HTML adapter for periodic DisplayWall refreshes."""

    def get(self, request: HttpRequest, wall_id: int) -> HttpResponse:
        """Render one current, tenant-scoped DisplayWall fragment."""
        snapshot = KioskService.get_wall_snapshot(wall_id, user=request.user)
        if snapshot is None:
            raise Http404("Wall not found")
        return render(
            request,
            "micboard/kiosk/display_content.html",
            {"snapshot": snapshot},
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
        health = KioskHealthService.get_wall_health(wall_id=wall_id, user=request.user)
        if health is None:
            return JsonResponse({"error": "Wall not found"}, status=404)
        return JsonResponse({"status": "ok", **health.model_dump(mode="json")})
