"""Gap analysis views for identifying missing data in hardware inventory."""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import path

from micboard.services.hardware.gap_analysis_service import get_gap_analysis_context


class HardwareGapAnalysisAdmin(admin.ModelAdmin):
    """Admin interface showing gaps in hardware data collection."""

    change_list_template = "admin/hardware_gap_analysis.html"

    def get_urls(self):
        """Add custom gap analysis URL."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "gap-analysis/",
                self.admin_site.admin_view(self.gap_analysis_view),
                name="hardware_gap_analysis",
            ),
        ]
        return custom_urls + urls

    def gap_analysis_view(self, request: HttpRequest) -> HttpResponse:
        """Display detailed gap analysis report."""
        context = get_gap_analysis_context().model_dump()
        return render(request, "admin/hardware_gap_analysis.html", context)


def gap_analysis_admin_display(request: HttpRequest) -> HttpResponse:
    """Standalone gap analysis view for dashboard."""
    context = get_gap_analysis_context().model_dump()
    return render(request, "admin/hardware_gap_analysis.html", context)
