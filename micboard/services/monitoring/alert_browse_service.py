"""Tenant-scoped alert-history page and statistics projections."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q, QuerySet

from micboard.models.monitoring.alert import Alert
from micboard.services.monitoring.alert_browse_dtos import (
    AlertBrowseCriteria,
    AlertBrowseItem,
    AlertBrowsePage,
    AlertBrowseRows,
    AlertBrowseStats,
)
from micboard.services.monitoring.alerts import get_alerts_for_user


class AlertBrowseDTOMapper:
    """Map eager-loaded alert rows to stable template DTOs."""

    @staticmethod
    def from_model(alert: Alert) -> AlertBrowseItem:
        """Project one alert without triggering related-object queries."""
        assignment = alert.assignment
        message_is_truncated = len(alert.message) > 50
        return AlertBrowseItem(
            id=alert.pk,
            created_at=alert.created_at,
            alert_type_label=alert.get_alert_type_display(),
            channel_label=str(alert.channel),
            performer_name=assignment.performer.name if assignment else None,
            user_display_name=alert.user.get_full_name() or alert.user.username,
            status=alert.status,
            status_label=alert.get_status_display(),
            message_preview=(f"{alert.message[:49]}…" if message_is_truncated else alert.message),
            message_is_truncated=message_is_truncated,
            is_overdue=alert.is_overdue,
        )


class AlertBrowseService:
    """Own alert filters, eager loading, pagination, and statistics."""

    PAGE_SIZE = 25

    @staticmethod
    def _visible_alerts(*, user: Any) -> QuerySet[Alert]:
        """Return the canonical recipient-private alert queryset."""
        return get_alerts_for_user(user)

    @classmethod
    def _filtered_alerts(
        cls,
        *,
        user: Any,
        criteria: AlertBrowseCriteria,
    ) -> QuerySet[Alert]:
        """Apply shared filters and eager loading for alert-row projections."""
        alerts = cls._visible_alerts(user=user).select_related(
            "assignment__performer",
            "assignment__wireless_unit__base_chassis__location",
            "channel__chassis",
            "user",
        )
        if criteria.status and criteria.status != "all":
            alerts = alerts.filter(status=criteria.status)
        if criteria.alert_type:
            alerts = alerts.filter(alert_type=criteria.alert_type)
        return alerts.order_by("-created_at", "-pk")

    @staticmethod
    def _normalize_page_number(page: int | str | None) -> int:
        """Return a positive page number without running a count query."""
        try:
            page_number = int(page or 1)
        except (TypeError, ValueError):
            return 1
        return max(page_number, 1)

    @classmethod
    def get_page(cls, *, user: Any, criteria: AlertBrowseCriteria) -> AlertBrowsePage:
        """Return one bounded page without computing history-wide statistics."""
        alerts = cls._filtered_alerts(user=user, criteria=criteria)

        page = Paginator(
            alerts,
            cls.PAGE_SIZE,
        ).get_page(criteria.page)
        first_page = max(1, page.number - 2)
        last_page = min(page.paginator.num_pages, page.number + 2)
        poll_query_string = urlencode(
            {
                "status": criteria.status,
                "type": criteria.alert_type,
                "page": page.number,
            }
        )
        return AlertBrowsePage(
            items=[AlertBrowseDTOMapper.from_model(alert) for alert in page.object_list],
            total_count=page.paginator.count,
            page_number=page.number,
            total_pages=page.paginator.num_pages,
            page_numbers=list(range(first_page, last_page + 1)),
            has_previous=page.has_previous(),
            has_next=page.has_next(),
            previous_page=page.previous_page_number() if page.has_previous() else None,
            next_page=page.next_page_number() if page.has_next() else None,
            status_filter=criteria.status,
            alert_type_filter=criteria.alert_type,
            poll_query_string=poll_query_string,
        )

    @classmethod
    def get_rows(cls, *, user: Any, criteria: AlertBrowseCriteria) -> AlertBrowseRows:
        """Return one live-refresh slice with no pagination count query."""
        page_number = cls._normalize_page_number(criteria.page)
        start = (page_number - 1) * cls.PAGE_SIZE
        stop = start + cls.PAGE_SIZE + 1
        alerts = list(cls._filtered_alerts(user=user, criteria=criteria)[start:stop])
        return AlertBrowseRows(
            items=[AlertBrowseDTOMapper.from_model(alert) for alert in alerts[: cls.PAGE_SIZE]],
            page_number=page_number,
            has_next=len(alerts) > cls.PAGE_SIZE,
        )

    @classmethod
    def get_stats(cls, *, user: Any) -> AlertBrowseStats:
        """Compute status totals for the full alert page only."""
        stats = cls._visible_alerts(user=user).aggregate(
            total=Count("pk"),
            pending=Count("pk", filter=Q(status="pending")),
            acknowledged=Count("pk", filter=Q(status="acknowledged")),
            resolved=Count("pk", filter=Q(status="resolved")),
            failed=Count("pk", filter=Q(status="failed")),
        )
        return AlertBrowseStats.model_validate(stats)
