"""Discovery job finalization and notification publication contracts."""

from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings

import pytest

from micboard.services.notification.device_broadcast_service import (
    DeviceSnapshotBroadcastService,
)
from micboard.services.sync.discovery_claim_service import DiscoverySyncClaimService
from micboard.services.sync.discovery_dtos import DiscoverySyncSummary
from micboard.services.sync.discovery_sync_service import DiscoverySyncService
from tests.factories.discovery import DiscoveryJobFactory, ManufacturerFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("errors", [[], ["first", "second"]])
def test_finalize_job_persists_metrics_status_and_bounded_note(errors: list[str]) -> None:
    manufacturer = ManufacturerFactory()
    job = DiscoveryJobFactory(manufacturer=manufacturer, status="running")
    summary = DiscoverySyncSummary(
        manufacturer=manufacturer.pk,
        missing_ips_submitted=2,
        scanned_ips_submitted=3,
        errors=errors,
    )

    assert DiscoverySyncClaimService.finalize(job, summary) is True

    job.refresh_from_db()
    assert summary.status == ("failed" if errors else "success")
    assert job.status == summary.status
    assert job.items_scanned == 5
    assert job.items_submitted == 5
    assert job.note == "; ".join(errors)
    assert job.finished_at is not None


def test_finalize_job_truncates_large_error_note() -> None:
    manufacturer = ManufacturerFactory()
    job = DiscoveryJobFactory(manufacturer=manufacturer, status="running")
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk, errors=["x" * 1100])

    assert DiscoverySyncClaimService.finalize(job, summary) is True

    job.refresh_from_db()
    assert len(job.note) == 1024


def test_finalize_job_does_not_overwrite_an_expired_claim() -> None:
    manufacturer = ManufacturerFactory()
    job = DiscoveryJobFactory(manufacturer=manufacturer, status="failed", note="expired")
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk)

    assert DiscoverySyncClaimService.finalize(job, summary) is False

    job.refresh_from_db()
    assert summary.status == "running"
    assert job.status == "failed"
    assert job.note == "expired"


def test_broadcast_results_publishes_chassis_projection() -> None:
    manufacturer = ManufacturerFactory()
    with patch.object(DeviceSnapshotBroadcastService, "broadcast") as broadcast:
        DiscoverySyncService.broadcast_results(manufacturer)

    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        namespace="discovery",
        max_devices=500,
        chunk_size=100,
    )


@pytest.mark.parametrize(
    ("max_devices", "chunk_size", "expected_max", "expected_chunk"),
    [(2, 1, 2, 1), (99_999, 99_999, 5_000, 500)],
)
def test_broadcast_results_honors_clamped_projection_limits(
    max_devices: int,
    chunk_size: int,
    expected_max: int,
    expected_chunk: int,
) -> None:
    manufacturer = ManufacturerFactory()
    with (
        override_settings(
            MICBOARD_POLL_MAX_DEVICES=max_devices,
            MICBOARD_POLL_BROADCAST_CHUNK_SIZE=chunk_size,
        ),
        patch.object(DeviceSnapshotBroadcastService, "broadcast") as broadcast,
    ):
        DiscoverySyncService.broadcast_results(manufacturer)

    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        namespace="discovery",
        max_devices=expected_max,
        chunk_size=expected_chunk,
    )


def test_broadcast_results_contains_notification_failure() -> None:
    manufacturer = ManufacturerFactory()
    with patch.object(
        DeviceSnapshotBroadcastService,
        "broadcast",
        side_effect=RuntimeError("database unavailable"),
    ):
        DiscoverySyncService.broadcast_results(manufacturer)
