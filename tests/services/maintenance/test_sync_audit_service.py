"""Manufacturer polling audit persistence contracts."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

from micboard.models.audit.activity_log import ServiceSyncLog
from micboard.services.maintenance.sync_audit_service import (
    ServiceSyncAuditDTO,
    ServiceSyncAuditService,
)
from tests.factories.discovery import ManufacturerFactory

pytestmark = pytest.mark.django_db


def test_sync_audit_persists_bounded_success_counts() -> None:
    """Successful polling writes one complete, secret-free operational row."""
    manufacturer = ManufacturerFactory()
    started_at = timezone.now() - timedelta(seconds=2)

    row = ServiceSyncAuditService.record_poll_result(
        manufacturer=manufacturer,
        started_at=started_at,
        result={
            "devices_created": 2,
            "devices_updated": 3,
            "devices_examined": 7,
            "device_limit": 500,
            "inventory_complete": True,
            "errors": [],
        },
    )

    assert row is not None
    assert row.status == "success"
    assert row.device_count == 7
    assert row.updated_count == 3
    assert row.error_message == ""
    assert row.details == {
        "created_count": 2,
        "device_limit": 500,
        "inventory_complete": True,
    }
    assert row.completed_at is not None
    assert row.completed_at >= started_at


def test_sync_audit_redacts_failures_and_normalizes_negative_counts() -> None:
    """Vendor errors are represented by counts without persisting their text."""
    manufacturer = ManufacturerFactory()
    private_error = "private vendor credential"

    row = ServiceSyncAuditService.record_poll_result(
        manufacturer=manufacturer,
        started_at=timezone.now(),
        result={
            "devices_created": -1,
            "devices_updated": -2,
            "devices_examined": -3,
            "inventory_complete": False,
            "errors": [private_error],
        },
    )

    assert row is not None
    assert row.status == "failed"
    assert row.device_count == 0
    assert row.updated_count == 0
    assert row.error_message == "Polling reported 1 error(s); details redacted."
    assert private_error not in str(row.details)
    assert private_error not in row.error_message


def test_sync_audit_dto_handles_non_list_error_contract() -> None:
    """A malformed but truthy error marker still produces a failed bounded DTO."""
    audit = ServiceSyncAuditDTO.from_poll_result(
        started_at=timezone.now(),
        result={"errors": "failed"},
    )

    assert audit.status == "failed"
    assert audit.error_count == 1


def test_sync_audit_contains_and_redacts_persistence_failure(caplog) -> None:
    """Audit storage failure cannot replace the manufacturer polling result."""
    manufacturer = ManufacturerFactory()
    private_error = "private database detail"

    with patch.object(
        ServiceSyncLog.objects,
        "using",
        side_effect=RuntimeError(private_error),
    ):
        row = ServiceSyncAuditService.record_poll_result(
            manufacturer=manufacturer,
            started_at=timezone.now(),
            result={"errors": []},
        )

    assert row is None
    assert private_error not in caplog.text
    assert "error details redacted" in caplog.text
