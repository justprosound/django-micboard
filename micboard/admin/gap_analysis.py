"""Gap analysis views for identifying missing data in hardware inventory."""

from django.contrib import admin
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import path

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.integrations import Accessory


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
        context = self.get_gap_analysis_context(request)
        return render(request, "admin/hardware_gap_analysis.html", context)

    @staticmethod
    def get_gap_analysis_context(request: HttpRequest) -> dict:
        """Generate gap analysis context for display."""
        total_chassis = WirelessChassis.objects.count()

        # Core data gaps
        missing_fields = {
            "IP Address": WirelessChassis.objects.filter(ip__isnull=True).count(),
            "Serial Number": WirelessChassis.objects.filter(serial_number__isnull=True).count(),
            "Model": WirelessChassis.objects.filter(model__isnull=True).count(),
            "Manufacturer": WirelessChassis.objects.filter(manufacturer__isnull=True).count(),
        }

        # Accessory gaps
        chassis_without_accessories = WirelessChassis.objects.annotate(
            accessory_count=Count("accessories")
        ).filter(accessory_count=0)

        accessory_by_type = Accessory.objects.values("category").annotate(
            total=Count("id"),
            unavailable=Count("id", filter=Q(is_available=False)),
            needs_repair=Count("id", filter=Q(condition="needs_repair")),
        )

        # Count by device type
        devices_by_model = (
            WirelessChassis.objects.values("model").annotate(count=Count("id")).order_by("-count")
        )

        devices_by_model_with_gaps = []
        for item in devices_by_model:
            model_name = item["model"]
            count = item["count"]
            model_devices = WirelessChassis.objects.filter(model=model_name)

            devices_by_model_with_gaps.append(
                {
                    "model": model_name,
                    "count": count,
                    "accessories_avg": (
                        model_devices.annotate(acc_count=Count("accessories")).aggregate(
                            avg=Count("accessories") / count
                        )["avg"]
                        if count > 0
                        else 0
                    ),
                    "missing_ip": model_devices.filter(ip__isnull=True).count(),
                    "without_accessories": model_devices.annotate(acc_count=Count("accessories"))
                    .filter(acc_count=0)
                    .count(),
                }
            )

        # Health check frequency
        last_polled_gap = WirelessChassis.objects.filter(last_polled__isnull=True).count()

        return {
            "title": "Hardware Inventory Gap Analysis",
            "total_chassis": total_chassis,
            "missing_fields": missing_fields,
            "missing_fields_pct": {
                k: round((v / total_chassis * 100) if total_chassis > 0 else 0, 1)
                for k, v in missing_fields.items()
            },
            "chassis_without_accessories": chassis_without_accessories.count(),
            "accessories_by_type": list(accessory_by_type),
            "devices_by_model_with_gaps": devices_by_model_with_gaps,
            "last_polled_gap": last_polled_gap,
            "needs_attention": {
                "high": chassis_without_accessories.count(),
                "medium": missing_fields["IP Address"],
                "low": chassis_without_accessories.count() > (total_chassis * 0.5),
            },
        }


def gap_analysis_admin_display(request: HttpRequest) -> HttpResponse:
    """Standalone gap analysis view for dashboard."""
    context = HardwareGapAnalysisAdmin.get_gap_analysis_context(request)
    return render(request, "admin/hardware_gap_analysis.html", context)
