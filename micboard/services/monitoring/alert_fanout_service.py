"""Bounded, fair, and authorization-aware alert fanout queries."""

from __future__ import annotations

import logging
from typing import Any, TypeVar, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import models
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from micboard.models.base_managers import TenantOptimizedQuerySet
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.monitoring.alert_fanout_dtos import AlertFanoutBudget
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

ALERT_FANOUT_CURSOR_TIMEOUT_SECONDS = 7 * 24 * 60 * 60

_ModelT = TypeVar("_ModelT", bound=models.Model)


class AlertFanoutService:
    """Select fair bounded fanout pages and revalidate recipients at delivery time."""

    @classmethod
    def assignments_for_unit(
        cls,
        *,
        unit: WirelessUnit,
        scope: str,
        budget: AlertFanoutBudget,
        offline_only: bool = False,
    ) -> list[PerformerAssignment]:
        """Return a rotating bounded page of active assignments for one unit."""
        limit = budget.remaining_assignments
        if limit <= 0:
            budget.assignments_truncated = True
            return []

        queryset = PerformerAssignment.objects.filter(
            wireless_unit_id=unit.pk,
            is_active=True,
            monitoring_group__is_active=True,
        ).select_related("performer", "monitoring_group")
        if offline_only:
            queryset = queryset.filter(alert_on_hardware_offline=True)

        items, truncated = cls._rotating_page(
            queryset,
            limit=limit,
            cursor_key=cls._assignment_cursor_key(unit_id=unit.pk, scope=scope),
        )
        budget.record_assignments(len(items), truncated=truncated)
        return items

    @classmethod
    def recipients_for_assignments(
        cls,
        *,
        unit: WirelessUnit,
        assignments: list[PerformerAssignment],
        scope: str,
        budget: AlertFanoutBudget,
    ) -> dict[int, list[Any]]:
        """Return active recipients for a bounded assignment page without N+1 queries."""
        limit = budget.remaining_recipients
        if limit <= 0:
            budget.recipients_truncated = True
            return {}
        if not assignments:
            return {}

        assignment_ids = [assignment.pk for assignment in assignments]
        queryset = PerformerAssignment.objects.filter(
            pk__in=assignment_ids,
            monitoring_group__is_active=True,
            monitoring_group__users__is_active=True,
        )
        pairs, truncated = cls._rotating_recipient_pairs(
            queryset,
            limit=limit,
            cursor_key=cls._recipient_cursor_key(
                unit_id=unit.pk,
                scope=scope,
            ),
        )
        budget.record_recipients(len(pairs), truncated=truncated)
        if not pairs:
            return {}

        user_model = get_user_model()
        users_by_id = (
            user_model._default_manager.filter(pk__in={user_id for _, user_id in pairs})
            .select_related("alert_preferences")
            .in_bulk()
        )
        recipients: dict[int, list[Any]] = {}
        for assignment_id, user_id in pairs:
            user = users_by_id.get(user_id)
            if user is not None:
                recipients.setdefault(assignment_id, []).append(user)
        return recipients

    @classmethod
    def current_authorized_recipient(
        cls,
        *,
        unit: WirelessUnit,
        assignment: PerformerAssignment,
        user: Any,
    ) -> Any | None:
        """Reload and authorize a recipient against the current assignment and tenant scope."""
        user_id = getattr(user, "pk", None)
        if unit.pk is None or assignment.pk is None or user_id is None:
            return None

        user_model = get_user_model()
        current_user = (
            user_model._default_manager.filter(pk=user_id, is_active=True)
            .select_related("alert_preferences")
            .first()
        )
        if current_user is None or not getattr(current_user, "is_authenticated", False):
            return None

        assignment_is_current = PerformerAssignment.objects.filter(
            pk=assignment.pk,
            wireless_unit_id=unit.pk,
            is_active=True,
            monitoring_group__is_active=True,
            monitoring_group__users=current_user,
        ).exists()
        if not assignment_is_current:
            return None
        if not cls.recipient_has_unit_scope(unit=unit, user=current_user):
            return None
        return current_user

    @staticmethod
    def recipient_has_unit_scope(*, unit: WirelessUnit, user: Any) -> bool:
        """Intersect an active authenticated recipient with the unit's tenant boundary."""
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return False
        if unit.pk is None:
            return False
        if not (
            getattr(settings, "MICBOARD_MSP_ENABLED", False)
            or getattr(settings, "MICBOARD_MULTI_SITE_MODE", False)
        ):
            return True

        tenant_units: QuerySet[WirelessUnit] = TenantOptimizedQuerySet(
            WirelessUnit,
            using=unit._state.db or WirelessUnit.objects.db,
        ).for_user(user=user)
        return tenant_units.filter(pk=unit.pk).exists()

    @classmethod
    def _rotating_page(
        cls,
        queryset: QuerySet[_ModelT],
        *,
        limit: int,
        cursor_key: str,
    ) -> tuple[list[_ModelT], bool]:
        """Read at most ``limit + 1`` rows and rotate deterministically by primary key."""
        cursor = cls._read_cursor(cursor_key)
        page = cast(
            list[_ModelT],
            list(
                queryset.annotate(
                    _alert_cursor_bucket=Case(
                        When(pk__gt=cursor, then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                ).order_by("_alert_cursor_bucket", "pk")[: limit + 1]
            ),
        )
        selected = page[:limit]
        truncated = len(page) > limit

        if selected:
            cls._write_cursor(cursor_key, selected[-1].pk)
        return selected, truncated

    @staticmethod
    def _assignment_cursor_key(*, unit_id: int | None, scope: str) -> str:
        return f"micboard:alert-fanout:v1:assignment:{scope}:{unit_id or 0}"

    @staticmethod
    def _recipient_cursor_key(*, unit_id: int | None, scope: str) -> str:
        return f"micboard:alert-fanout:v1:recipient:{scope}:{unit_id or 0}"

    @classmethod
    def _rotating_recipient_pairs(
        cls,
        queryset: QuerySet[PerformerAssignment],
        *,
        limit: int,
        cursor_key: str,
    ) -> tuple[list[tuple[int, int]], bool]:
        """Return one circular, lexicographically ordered assignment-recipient page."""
        assignment_cursor, user_cursor = cls._read_pair_cursor(cursor_key)
        after_cursor = Q(pk__gt=assignment_cursor) | Q(
            pk=assignment_cursor,
            monitoring_group__users__pk__gt=user_cursor,
        )
        page = cast(
            list[tuple[int, int]],
            list(
                queryset.annotate(
                    _alert_cursor_bucket=Case(
                        When(after_cursor, then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                )
                .order_by(
                    "_alert_cursor_bucket",
                    "pk",
                    "monitoring_group__users__pk",
                )
                .values_list("pk", "monitoring_group__users__pk")[: limit + 1]
            ),
        )
        selected = page[:limit]
        if selected:
            cls._write_pair_cursor(cursor_key, selected[-1])
        return selected, len(page) > limit

    @staticmethod
    def _read_cursor(key: str) -> int:
        """Read a cursor while keeping alert evaluation available during cache outages."""
        try:
            value = cache.get(key, 0)
        except Exception as exc:
            logger.exception(
                "Could not read an alert fanout cursor",
                exc_info=sanitized_exception_info(exc),
            )
            return 0
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return 0
        return value

    @staticmethod
    def _write_cursor(key: str, value: int) -> None:
        """Persist a cursor without making alert delivery cache-dependent."""
        try:
            cache.set(key, value, timeout=ALERT_FANOUT_CURSOR_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.exception(
                "Could not persist an alert fanout cursor",
                exc_info=sanitized_exception_info(exc),
            )

    @staticmethod
    def _read_pair_cursor(key: str) -> tuple[int, int]:
        """Read a validated composite cursor without making fanout cache-dependent."""
        try:
            value = cache.get(key, (0, 0))
        except Exception as exc:
            logger.exception(
                "Could not read an alert recipient cursor",
                exc_info=sanitized_exception_info(exc),
            )
            return 0, 0
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value
            )
        ):
            return 0, 0
        return value

    @staticmethod
    def _write_pair_cursor(key: str, value: tuple[int, int]) -> None:
        """Persist a composite recipient cursor while tolerating cache outages."""
        try:
            cache.set(key, value, timeout=ALERT_FANOUT_CURSOR_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.exception(
                "Could not persist an alert recipient cursor",
                exc_info=sanitized_exception_info(exc),
            )
