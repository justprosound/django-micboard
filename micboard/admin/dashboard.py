"""Django admin dashboard for system platform status.

Provides real-time overview of manufacturers, devices, and service health.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from micboard.decorators import rate_limit_view
from micboard.models import (
    ActivityLog,
    Manufacturer,
    RFChannel,
    ServiceSyncLog,
    WirelessChassis,
    WirelessUnit,
)
from micboard.services.efis_import import EFISImportService
from micboard.services.manufacturer_service import get_all_services

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
@rate_limit_view(max_requests=60, window_seconds=60)
def admin_dashboard(request) -> render:
    """Main admin dashboard showing system platform status.

    Displays:
    - Overall device counts and online status
    - Manufacturer service health
    - Recent activity
    - System statistics
    """
    # Get time ranges for activity stats
    now = timezone.now()
    last_hour = now - timedelta(hours=1)
    last_day = now - timedelta(days=1)
    last_week = now - timedelta(days=7)

    # Device statistics
    all_receivers = WirelessChassis.objects.all()
    all_transmitters = WirelessUnit.objects.all()

    receiver_stats = {
        "total": all_receivers.count(),
        "online": all_receivers.filter(is_online=True).count(),
        "offline": all_receivers.filter(is_online=False).count(),
        "active": all_receivers.filter(status__in=["online", "degraded", "provisioning"]).count(),
    }

    transmitter_stats = {
        "total": all_transmitters.count(),
        "online": all_transmitters.filter(status="online").count(),
        "offline": all_transmitters.filter(status="offline").count(),
        "active": all_transmitters.filter(
            status__in=["online", "degraded", "provisioning"]
        ).count(),
    }

    # Manufacturer statistics
    manufacturers = Manufacturer.objects.annotate(
        receiver_count=Count("wirelesschassis", distinct=True),
        transmitter_count=Count("wirelessunit", distinct=True),
        online_receivers=Count(
            "wirelesschassis",
            filter=Q(wirelesschassis__is_online=True),
            distinct=True,
        ),
        online_transmitters=Count(
            "wirelessunit",
            filter=Q(wirelessunit__status="online"),
            distinct=True,
        ),
    )

    manufacturer_stats = []
    service_health = {}

    for mfg in manufacturers:
        stats = {
            "id": mfg.id,
            "code": mfg.code,
            "name": mfg.name,
            "receiver_count": mfg.receiver_count,
            "transmitter_count": mfg.transmitter_count,
            "online_receivers": mfg.online_receivers,
            "online_transmitters": mfg.online_transmitters,
            "total_online": mfg.online_receivers + mfg.online_transmitters,
        }

        # Get service health
        service = None
        try:
            for svc in get_all_services():
                if svc.code == mfg.code:
                    service = svc
                    break
        except Exception as e:
            logger.warning(f"Error getting service health for {mfg.code}: {e}")

        if service:
            health = service.check_health()
            stats["service_status"] = health.get("status", "unknown")
            stats["service_message"] = health.get("message", "")
            stats["last_poll"] = service.last_poll.isoformat() if service.last_poll else None
            stats["error_count"] = service.error_count
        else:
            stats["service_status"] = "unavailable"
            stats["service_message"] = "Service not loaded"
            stats["last_poll"] = None
            stats["error_count"] = 0

        manufacturer_stats.append(stats)
        service_health[mfg.code] = stats["service_status"]

    # Activity statistics
    activity_last_hour = ActivityLog.objects.filter(created_at__gte=last_hour).count()
    activity_last_day = ActivityLog.objects.filter(created_at__gte=last_day).count()
    activity_last_week = ActivityLog.objects.filter(created_at__gte=last_week).count()

    activity_by_type = (
        ActivityLog.objects.filter(created_at__gte=last_day)
        .values("activity_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    activity_by_status = (
        ActivityLog.objects.filter(created_at__gte=last_day)
        .values("status")
        .annotate(count=Count("id"))
    )

    # Recent activities
    recent_activities = ActivityLog.objects.select_related("user", "content_type").order_by(
        "-created_at"
    )[:10]

    recent_activities_data = []
    for activity in recent_activities:
        recent_activities_data.append(
            {
                "summary": activity.summary,
                "activity_type": activity.get_activity_type_display(),
                "operation": activity.get_operation_display(),
                "status": activity.status,
                "user": activity.user.username if activity.user else activity.service_code,
                "created_at": activity.created_at.isoformat(),
            }
        )

    # Recent syncs
    recent_syncs = ServiceSyncLog.objects.select_related("service").order_by("-started_at")[:5]

    recent_syncs_data = []
    for sync in recent_syncs:
        recent_syncs_data.append(
            {
                "service": sync.service.name,
                "sync_type": sync.get_sync_type_display(),
                "status": sync.status,
                "device_count": sync.device_count,
                "online_count": sync.online_count,
                "duration": sync.duration_seconds(),
                "started_at": sync.started_at.isoformat(),
                "completed_at": sync.completed_at.isoformat() if sync.completed_at else None,
            }
        )

    # Channel statistics
    channel_stats = {
        "total": RFChannel.objects.count(),
        "active": RFChannel.objects.filter(enabled=True).count(),
    }

    # System health summary
    system_health = {
        "status": "healthy",
        "total_devices": receiver_stats["total"] + transmitter_stats["total"],
        "online_devices": receiver_stats["online"] + transmitter_stats["online"],
        "online_percentage": (
            round(
                100
                * (receiver_stats["online"] + transmitter_stats["online"])
                / (receiver_stats["total"] + transmitter_stats["total"])
            )
            if (receiver_stats["total"] + transmitter_stats["total"]) > 0
            else 0
        ),
        "active_manufacturers": manufacturers.filter(receiver_count__gt=0).count(),
        "service_issues": sum(1 for s in service_health.values() if s != "healthy"),
    }

    if system_health["service_issues"] > 0:
        system_health["status"] = "degraded"
    if system_health["online_percentage"] < 50:
        system_health["status"] = "unhealthy"

    # Check compliance data freshness
    efis_outdated = EFISImportService.is_outdated()
    efis_last_update = EFISImportService.get_last_import_date()

    context = {
        "title": "Micboard Admin Dashboard",
        "system_health": system_health,
        "receiver_stats": receiver_stats,
        "transmitter_stats": transmitter_stats,
        "channel_stats": channel_stats,
        "manufacturer_stats": manufacturer_stats,
        "activity_stats": {
            "last_hour": activity_last_hour,
            "last_day": activity_last_day,
            "last_week": activity_last_week,
            "by_type": list(activity_by_type),
            "by_status": list(activity_by_status),
        },
        "recent_activities": recent_activities_data,
        "recent_syncs": recent_syncs_data,
        "timestamp": now.isoformat(),
        "efis_alert": {
            "outdated": efis_outdated,
            "last_update": efis_last_update,
        },
    }

    return render(request, "admin/dashboard.html", context)


@login_required
@require_http_methods(["GET"])
@rate_limit_view(max_requests=60, window_seconds=60)
def api_dashboard_data(request) -> JsonResponse:
    """API endpoint for dashboard data (JSON).

    Used for AJAX updates and external integrations.
    """
    now = timezone.now()
    last_hour = now - timedelta(hours=1)

    # Get current statistics
    all_receivers = WirelessChassis.objects.all()
    all_transmitters = WirelessUnit.objects.all()

    receiver_stats = {
        "total": all_receivers.count(),
        "online": all_receivers.filter(is_online=True).count(),
        "offline": all_receivers.filter(is_online=False).count(),
    }

    transmitter_stats = {
        "total": all_transmitters.count(),
        "online": all_transmitters.filter(status="online").count(),
        "offline": all_transmitters.filter(status="offline").count(),
    }

    # Service health
    service_health = {}
    try:
        for service in get_all_services():
            health = service.check_health()
            service_health[service.code] = {
                "status": health.get("status"),
                "message": health.get("message"),
                "last_poll": service.last_poll.isoformat() if service.last_poll else None,
            }
    except Exception as e:
        logger.warning(f"Error getting service health: {e}")

    # Recent activities
    recent_activities = (
        ActivityLog.objects.filter(created_at__gte=last_hour)
        .values("activity_type", "status")
        .annotate(count=Count("id"))
    )

    return JsonResponse(
        {
            "timestamp": now.isoformat(),
            "receivers": receiver_stats,
            "transmitters": transmitter_stats,
            "services": service_health,
            "recent_activities": list(recent_activities),
        }
    )


@login_required
@require_http_methods(["GET"])
@rate_limit_view(max_requests=120, window_seconds=60)
def api_manufacturer_status(request, manufacturer_code: str) -> JsonResponse:
    """API endpoint for detailed manufacturer status."""
    try:
        manufacturer = Manufacturer.objects.get(code=manufacturer_code)
    except Manufacturer.DoesNotExist:
        return JsonResponse(
            {"error": f"Manufacturer not found: {manufacturer_code}"},
            status=404,
        )

    receivers = manufacturer.wirelesschassis_set.all()
    transmitters = manufacturer.wirelessunit_set.all()

    receiver_stats = {
        "total": receivers.count(),
        "online": receivers.filter(is_online=True).count(),
        "offline": receivers.filter(is_online=False).count(),
        "active": receivers.filter(status__in=["online", "degraded", "provisioning"]).count(),
    }

    transmitter_stats = {
        "total": transmitters.count(),
        "online": transmitters.filter(status="online").count(),
        "offline": transmitters.filter(status="offline").count(),
        "active": transmitters.filter(status__in=["online", "degraded", "provisioning"]).count(),
    }

    # Recent syncs
    recent_syncs = manufacturer.sync_logs.all().order_by("-started_at")[:5]

    recent_syncs_data = [
        {
            "sync_type": sync.get_sync_type_display(),
            "status": sync.status,
            "device_count": sync.device_count,
            "online_count": sync.online_count,
            "duration": sync.duration_seconds(),
            "started_at": sync.started_at.isoformat(),
        }
        for sync in recent_syncs
    ]

    # Recent activities
    recent_activities = ActivityLog.objects.filter(
        Q(service_code=manufacturer_code) | Q(object_id=manufacturer.id)
    ).order_by("-created_at")[:5]

    recent_activities_data = [
        {
            "summary": activity.summary,
            "activity_type": activity.get_activity_type_display(),
            "status": activity.status,
            "created_at": activity.created_at.isoformat(),
        }
        for activity in recent_activities
    ]

    return JsonResponse(
        {
            "manufacturer": {
                "id": manufacturer.id,
                "code": manufacturer.code,
                "name": manufacturer.name,
            },
            "receivers": receiver_stats,
            "transmitters": transmitter_stats,
            "recent_syncs": recent_syncs_data,
            "recent_activities": recent_activities_data,
            "timestamp": timezone.now().isoformat(),
        }
    )
