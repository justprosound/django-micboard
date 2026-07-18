"""Tenant-safe integration with the optional sortable admin package."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db import IntegrityError, router, transaction
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
)

from micboard.admin.mixins import MicboardModelAdmin
from micboard.utils.dependencies import HAS_ADMIN_SORTABLE
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)
_UNSET = object()

if HAS_ADMIN_SORTABLE:
    from adminsortable2.admin import SortableAdminMixin as BaseSortableAdmin
else:

    class BaseSortableAdmin:  # type: ignore
        pass


class MicboardSortableAdmin(BaseSortableAdmin, MicboardModelAdmin):  # type: ignore[misc]
    """Sortable admin with tenant-scoped, primary-routed atomic writes."""

    _change_list_template_override: Any = _UNSET

    @property
    def change_list_template(self) -> Any:
        """Compose the sortable base template with an explicit override."""
        if self._change_list_template_override is not _UNSET:
            return self._change_list_template_override
        return super().change_list_template

    @change_list_template.setter
    def change_list_template(self, value: Any) -> None:
        self._change_list_template_override = value

    def get_actions(self, request: Any) -> dict[str, Any]:
        """Exclude upstream page moves that calculate ranks from global rows."""
        actions = super().get_actions(request)
        for action_name in (
            "move_to_exact_page",
            "move_to_back_page",
            "move_to_forward_page",
            "move_to_first_page",
            "move_to_last_page",
        ):
            actions.pop(action_name, None)
        return cast(dict[str, Any], actions)

    def _parse_updated_items(self, body: bytes) -> dict[Any, Any]:
        """Validate one sortable payload and normalize its model field values."""
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("sortable payload must be an object")
        updated_items = payload.get("updatedItems")
        if not isinstance(updated_items, list) or not updated_items:
            raise ValueError("updatedItems must be a non-empty list")

        primary_key_field = self.model._meta.pk
        order_field = self.model._meta.get_field(self.default_order_field)
        requested_orders: dict[Any, Any] = {}
        for item in updated_items:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError("each updated item must contain a primary key and order")
            primary_key = primary_key_field.to_python(item[0])
            order = order_field.to_python(item[1])
            if primary_key is None or order is None or primary_key in requested_orders:
                raise ValueError("updated items must contain unique, non-null values")
            requested_orders[primary_key] = order
        return requested_orders

    def update_order(self, request: Any) -> HttpResponse:
        """Atomically reorder only rows writable on the primary database."""
        if request.method != "POST":
            return HttpResponseNotAllowed(f"Method {request.method} not allowed")
        if not self.has_change_permission(request):
            return HttpResponseForbidden("Missing permissions to perform this request")

        using = router.db_for_write(self.model)
        try:
            requested_orders = self._parse_updated_items(request.body)

            with transaction.atomic(using=using):
                writable_rows = list(
                    self.get_queryset(request)
                    .using(using)
                    .select_for_update()
                    .filter(pk__in=requested_orders)
                )
                if {row.pk for row in writable_rows} != set(requested_orders):
                    return HttpResponseBadRequest("Invalid sortable row scope")
                for row in writable_rows:
                    setattr(row, self.default_order_field, requested_orders[row.pk])
                self.model._default_manager.using(using).bulk_update(
                    writable_rows,
                    [self.default_order_field],
                )
        except (IntegrityError, TypeError, ValidationError, ValueError) as exc:
            logger.exception(
                "Sortable update failed for %s",
                self.model._meta.label,
                exc_info=sanitized_exception_info(exc),
            )
            return HttpResponseBadRequest("Invalid sortable update")

        return HttpResponse(f"Updated {len(writable_rows)} items")
