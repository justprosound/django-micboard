"""Bounded, fair, and authorization-aware alert fanout queries."""

from typing import Any, TypeVar

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q, QuerySet

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.monitoring.alert_fanout_dtos import AlertFanoutBudget
from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.services.shared.fair_page_cursor import (
    fair_page,
    fair_page_rows,
    pair_cursor,
    position_cursor,
    read_cursor,
    write_cursor,
)
from micboard.services.shared.visibility import visible_to

ALERT_FANOUT_CURSOR_TIMEOUT_SECONDS = 7 * 24 * 60 * 60
_ASSIGNMENT_CURSOR = position_cursor(
    "alert fanout cursor", timeout=ALERT_FANOUT_CURSOR_TIMEOUT_SECONDS
)
_RECIPIENT_CURSOR = pair_cursor(
    "alert recipient cursor", timeout=ALERT_FANOUT_CURSOR_TIMEOUT_SECONDS
)

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
        if not cls.recipient_has_alert_scope(unit=unit, user=current_user):
            return None
        return current_user

    @staticmethod
    def recipient_has_alert_scope(*, unit: WirelessUnit, user: Any) -> bool:
        """Intersect an active recipient with both boundaries a delivered alert crosses.

        A delivered alert is attached to the unit's assigned RF channel, and the read path
        scopes alerts through ``channel__chassis``, while the unit's own boundary is reached
        through ``base_chassis``. Those resolve to the same building for a unit assigned to a
        channel on its own chassis and to different buildings as soon as it is not — nothing
        below the admin forms enforces same-chassis assignment. Authorizing only the unit
        would therefore let delivery persist an alert its own recipient cannot read.
        """
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return False
        if unit.pk is None:
            return False
        if not (micboard_settings.msp_enabled or micboard_settings.multi_site_mode):
            return True

        database = unit._state.db or WirelessUnit.objects.db
        tenant_units: QuerySet[WirelessUnit] = visible_to(
            WirelessUnit,
            user=user,
            using=database,
        )
        if not tenant_units.filter(pk=unit.pk).exists():
            return False

        channel = unit.assigned_resource
        if channel is None:
            return True

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        return (
            visible_to(WirelessChassis, user=user, using=database)
            .filter(pk=channel.chassis_id)
            .exists()
        )

    @classmethod
    def _rotating_page(
        cls,
        queryset: QuerySet[_ModelT],
        *,
        limit: int,
        cursor_key: str,
    ) -> tuple[list[_ModelT], bool]:
        """Read at most ``limit + 1`` rows and rotate deterministically by primary key."""
        cursor = read_cursor(_ASSIGNMENT_CURSOR, cursor_key)
        selected, truncated = fair_page(queryset, after=Q(pk__gt=cursor), limit=limit)
        if selected:
            write_cursor(_ASSIGNMENT_CURSOR, cursor_key, selected[-1].pk)
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
        assignment_cursor, user_cursor = read_cursor(_RECIPIENT_CURSOR, cursor_key)
        after_cursor = Q(pk__gt=assignment_cursor) | Q(
            pk=assignment_cursor,
            monitoring_group__users__pk__gt=user_cursor,
        )
        rows, truncated = fair_page_rows(
            queryset,
            after=after_cursor,
            order_by=("pk", "monitoring_group__users__pk"),
            fields=("pk", "monitoring_group__users__pk"),
            limit=limit,
        )
        selected = [(int(assignment_id), int(user_id)) for assignment_id, user_id in rows]
        if selected:
            write_cursor(_RECIPIENT_CURSOR, cursor_key, selected[-1])
        return selected, truncated
