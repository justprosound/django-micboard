"""Manufacturer lifecycle side-effect contracts."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from micboard.services.maintenance.audit import AuditService
from micboard.services.manufacturer.signals import (
    handle_manufacturer_delete,
    handle_manufacturer_save,
)


def _manufacturer(*, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        pk=7,
        name="Test Manufacturer",
        code="test-manufacturer",
        is_active=is_active,
    )


@pytest.mark.parametrize(
    ("created", "old_active", "is_active", "expected_operation", "should_discover"),
    [
        (True, None, True, "create", False),
        (False, False, True, "update", True),
        (False, True, True, "update", False),
        (False, False, False, "update", False),
    ],
)
def test_save_audits_and_returns_activation_transition(
    *,
    created: bool,
    old_active: bool | None,
    is_active: bool,
    expected_operation: str,
    should_discover: bool,
) -> None:
    """Discovery is requested only for a persisted inactive-to-active update."""
    manufacturer = _manufacturer(is_active=is_active)

    with patch.object(AuditService, "log_activity") as log_activity:
        result = handle_manufacturer_save(
            manufacturer=manufacturer,
            created=created,
            old_active=old_active,
            using="replica",
        )

    assert result is should_discover
    assert log_activity.call_args.kwargs["operation"] == expected_operation
    assert log_activity.call_args.kwargs["using"] == "replica"


def test_save_contains_audit_failure_without_changing_activation_result(caplog) -> None:
    """Audit backend failure cannot suppress required discovery scheduling."""
    manufacturer = _manufacturer()

    with patch.object(AuditService, "log_activity", side_effect=RuntimeError("private")):
        result = handle_manufacturer_save(
            manufacturer=manufacturer,
            created=False,
            old_active=False,
        )

    assert result is True
    assert "private" not in caplog.text
    assert "error details redacted" in caplog.text


def test_delete_audits_and_contains_audit_failure(caplog) -> None:
    """Deletion logging uses its database alias and safely contains backend failure."""
    manufacturer = _manufacturer()

    with patch.object(AuditService, "log_activity") as log_activity:
        handle_manufacturer_delete(manufacturer=manufacturer, using="replica")

    assert log_activity.call_args.kwargs["operation"] == "delete"
    assert log_activity.call_args.kwargs["using"] == "replica"

    with patch.object(AuditService, "log_activity", side_effect=RuntimeError("private")):
        handle_manufacturer_delete(manufacturer=manufacturer)

    assert "private" not in caplog.text
    assert "error details redacted" in caplog.text
