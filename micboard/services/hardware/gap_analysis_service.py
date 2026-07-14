"""Service functions for hardware gap analysis and reporting.

Provides gap analysis, inventory reporting, and data quality assessment
separated from the admin layer per architectural guidelines.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.integrations import Accessory
from micboard.services.hardware.dtos import (
    AccessoryTypeDTO,
    GapAnalysisDTO,
)


def get_gap_analysis_context() -> GapAnalysisDTO:
    """Generate gap analysis context for display.

    Returns:
        GapAnalysisDTO containing gap analysis data for template rendering.
    """
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

    # Convert accessory queryset to DTOs
    accessory_dtos = [
        AccessoryTypeDTO(
            category=item["category"] or "unknown",
            total=item["total"],
            unavailable=item["unavailable"],
            needs_repair=item["needs_repair"],
        )
        for item in accessory_by_type
    ]

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
    last_polled_gap = WirelessChassis.objects.filter(last_seen__isnull=True).count()

    return GapAnalysisDTO(
        title="Hardware Inventory Gap Analysis",
        total_chassis=total_chassis,
        missing_fields=missing_fields,
        missing_fields_pct={
            k: round((v / total_chassis * 100) if total_chassis > 0 else 0, 1)
            for k, v in missing_fields.items()
        },
        chassis_without_accessories=chassis_without_accessories.count(),
        accessories_by_type=accessory_dtos,
        devices_by_model_with_gaps=devices_by_model_with_gaps,
        last_polled_gap=last_polled_gap,
        needs_attention={
            "high": chassis_without_accessories.count(),
            "medium": missing_fields["IP Address"],
            "low": chassis_without_accessories.count() > (total_chassis * 0.5),
        },
    )


def get_gap_analysis_summary() -> dict[str, Any]:
    """Get a simplified summary of gap analysis data.

    Returns:
        Dictionary with key gap analysis metrics.
    """
    context = get_gap_analysis_context()
    return {
        "total_chassis": context.total_chassis,
        "chassis_without_accessories": context.chassis_without_accessories,
        "missing_ip_addresses": context.missing_fields["IP Address"],
        "last_polled_gap": context.last_polled_gap,
        "needs_attention_high": context.needs_attention["high"],
    }
