"""Django admin customizations for Manufacturer model.

Provides a custom admin view to manage discovery IPs for manufacturers.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models import Manufacturer
from micboard.services.discovery_service_new import DiscoveryService

logger = logging.getLogger(__name__)


@admin.register(Manufacturer)
class ManufacturerAdmin(MicboardModelAdmin):
    """Admin for Manufacturer with a view to manage discovery IPs."""

    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:manufacturer_id>/discovery-ips/",
                self.admin_site.admin_view(self.discovery_ips_view),
                name="micboard_manufacturer_discovery_ips",
            ),
        ]
        return custom_urls + urls

    def discovery_ips_view(self, request, manufacturer_id: int):
        """Display and manage discovery IPs for a manufacturer.

        GET: Show current discovery IPs.
        POST: Remove selected IP(s).
        """
        try:
            manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        except Manufacturer.DoesNotExist:
            self.message_user(
                request,
                f"Manufacturer with ID {manufacturer_id} not found",
                level=messages.ERROR,
            )
            return redirect("admin:micboard_manufacturer_changelist")

        discovery_service = DiscoveryService()  # Instantiate DiscoveryService

        ips: list[str] = []  # Initialize ips once

        if request.method == "POST":
            ips_to_remove = request.POST.getlist("remove_ip") or request.POST.getlist("remove_ips")
            ips_to_remove = [ip for ip in ips_to_remove if ip]
            if ips_to_remove:
                success_count = 0
                for ip in ips_to_remove:
                    if discovery_service.remove_discovery_candidate(ip, manufacturer):
                        success_count += 1

                if success_count > 0:
                    self.message_user(
                        request, f"Removed {success_count} IP(s)", level=messages.SUCCESS
                    )
                else:
                    self.message_user(request, "Failed to remove IP(s)", level=messages.ERROR)
            else:
                self.message_user(
                    request, "No IPs specified or client unavailable", level=messages.WARNING
                )

            return redirect(
                reverse("admin:micboard_manufacturer_discovery_ips", args=[manufacturer_id])
            )

        # For GET requests, or after POST if not redirected
        try:
            ips = discovery_service.get_discovery_candidates(manufacturer.code)
        except Exception as e:
            logger.exception("Failed to fetch discovery IPs for %s: %s", manufacturer.code, e)
            self.message_user(request, f"Failed to fetch discovery IPs: {e}", level=messages.ERROR)

        context: dict[str, Any] = {
            "manufacturer": manufacturer,
            "ips": ips,
            "opts": self.model._meta,
            "title": f"Discovery IPs for {manufacturer.name}",
            "show_refresh": getattr(request, "user", None)
            and getattr(request.user, "is_staff", False),
        }
        return render(request, "admin/micboard/manufacturer_discovery_ips.html", context)
