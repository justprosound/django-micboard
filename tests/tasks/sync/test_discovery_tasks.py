"""Coverage for thin Huey boundaries and their discovery execution service."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, call, patch

from django.utils import timezone

import pytest
from huey.exceptions import RetryTask

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.sync.discovery_dtos import (
    DiscoveryReconciliationResult,
    DiscoverySourceReconciliation,
)
from micboard.services.sync.discovery_execution_service import (
    MANUFACTURER_INACTIVE_REASON,
    MANUFACTURER_STATUS_CHECK_FAILURE_REASON,
    DiscoveryExecutionService,
)
from micboard.tasks.sync import discovery as discovery_tasks
from tests.factories.discovery import DiscoveryJobFactory, ManufacturerFactory


@pytest.fixture(autouse=True)
def active_manufacturer_boundary(monkeypatch) -> None:
    """Keep unit doubles active unless a test exercises stale-work rejection."""
    monkeypatch.setattr(
        "micboard.services.sync.discovery_execution_service."
        "ManufacturerActivationService.is_active",
        Mock(return_value=True),
    )


def test_run_manufacturer_reconciles_with_bounded_scan_size() -> None:
    manufacturer = SimpleNamespace(code="vendor")
    job = SimpleNamespace(pk=1)
    claim_service = SimpleNamespace(
        claim=Mock(return_value=(manufacturer, job)),
        finalize=Mock(return_value=True),
    )
    candidate_service = SimpleNamespace(
        run_manufacturer_discovery=Mock(
            return_value=DiscoverySourceReconciliation(
                manufacturer=32,
                success=True,
                sources_complete=True,
                remote_source_complete=True,
                additions_succeeded=True,
                removals_succeeded=True,
            )
        )
    )
    with (
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoverySyncClaimService",
            return_value=claim_service,
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoveryService",
            return_value=candidate_service,
        ),
    ):
        outcome = DiscoveryExecutionService.run_manufacturer(
            32,
            scan_cidrs=True,
            scan_fqdns=False,
        )

    candidate_service.run_manufacturer_discovery.assert_called_once_with(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=False,
        max_hosts=1024,
    )
    claim_service.claim.assert_called_once_with(32)
    claim_service.finalize.assert_called_once()
    assert claim_service.finalize.call_args.args[0] is job
    assert claim_service.finalize.call_args.args[1].errors == []
    assert outcome.status == "success"


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param("missing", id="missing-manufacturer"),
        pytest.param(RuntimeError("vendor unavailable"), id="unexpected-failure"),
    ],
)
def test_run_manufacturer_contains_failures(failure: object) -> None:
    side_effect = Manufacturer.DoesNotExist() if failure == "missing" else failure
    with patch(
        "micboard.services.sync.discovery_execution_service.DiscoverySyncClaimService"
    ) as claim_service_class:
        claim_service_class.return_value.claim.side_effect = side_effect
        outcome = DiscoveryExecutionService.run_manufacturer(
            33,
            scan_cidrs=False,
            scan_fqdns=True,
        )

        claim_service_class.return_value.finalize.assert_not_called()
        assert outcome.status == "failed"


def test_run_manufacturer_finalizes_failed_reconciliation() -> None:
    manufacturer = SimpleNamespace(code="vendor")
    job = SimpleNamespace(pk=2)
    claim_service = SimpleNamespace(
        claim=Mock(return_value=(manufacturer, job)),
        finalize=Mock(return_value=True),
    )
    candidate_service = SimpleNamespace(
        run_manufacturer_discovery=Mock(side_effect=RuntimeError("vendor unavailable"))
    )

    with (
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoverySyncClaimService",
            return_value=claim_service,
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoveryService",
            return_value=candidate_service,
        ),
    ):
        outcome = DiscoveryExecutionService.run_manufacturer(
            34,
            scan_cidrs=False,
            scan_fqdns=False,
        )

    summary = claim_service.finalize.call_args.args[1]
    assert summary.errors == ["vendor_reconciliation_failed"]
    assert outcome.status == "failed"


def test_run_manufacturer_finalizes_without_outbound_work_after_deactivation(
    monkeypatch,
) -> None:
    """A manufacturer disabled after its claim cannot reach the vendor transport."""
    manufacturer = SimpleNamespace(code="vendor")
    job = SimpleNamespace(pk=2)
    claim_service = SimpleNamespace(
        claim=Mock(return_value=(manufacturer, job)),
        finalize=Mock(return_value=True),
    )
    candidate_service = Mock()
    monkeypatch.setattr(
        "micboard.services.sync.discovery_execution_service."
        "ManufacturerActivationService.is_active",
        Mock(return_value=False),
    )

    with (
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoverySyncClaimService",
            return_value=claim_service,
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoveryService",
            return_value=candidate_service,
        ),
    ):
        outcome = DiscoveryExecutionService.run_manufacturer(
            34,
            scan_cidrs=False,
            scan_fqdns=False,
        )

    candidate_service.run_manufacturer_discovery.assert_not_called()
    summary = claim_service.finalize.call_args.args[1]
    assert summary.errors == [MANUFACTURER_INACTIVE_REASON]
    assert outcome.reason == MANUFACTURER_INACTIVE_REASON


def test_run_manufacturer_finalizes_when_activation_recheck_fails(monkeypatch) -> None:
    """A status-query outage fails closed and releases the discovery claim."""
    manufacturer = SimpleNamespace(code="vendor")
    job = SimpleNamespace(pk=2)
    claim_service = SimpleNamespace(
        claim=Mock(return_value=(manufacturer, job)),
        finalize=Mock(return_value=True),
    )
    candidate_service = Mock()
    monkeypatch.setattr(
        "micboard.services.sync.discovery_execution_service."
        "ManufacturerActivationService.is_active",
        Mock(side_effect=RuntimeError("database unavailable")),
    )

    with (
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoverySyncClaimService",
            return_value=claim_service,
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoveryService",
            return_value=candidate_service,
        ),
    ):
        outcome = DiscoveryExecutionService.run_manufacturer(
            34,
            scan_cidrs=False,
            scan_fqdns=False,
        )

    candidate_service.run_manufacturer_discovery.assert_not_called()
    summary = claim_service.finalize.call_args.args[1]
    assert summary.errors == [MANUFACTURER_STATUS_CHECK_FAILURE_REASON]
    assert outcome.reason == MANUFACTURER_STATUS_CHECK_FAILURE_REASON


def test_run_manufacturer_records_contained_vendor_write_failure() -> None:
    manufacturer = SimpleNamespace(code="vendor")
    claim_service = SimpleNamespace(
        claim=Mock(return_value=(manufacturer, SimpleNamespace(pk=3))),
        finalize=Mock(return_value=True),
    )
    candidate_service = SimpleNamespace(
        run_manufacturer_discovery=Mock(
            return_value=DiscoverySourceReconciliation(
                manufacturer=35,
                success=False,
                sources_complete=True,
                remote_source_complete=True,
                additions_succeeded=False,
                removals_succeeded=True,
            )
        )
    )

    with (
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoverySyncClaimService",
            return_value=claim_service,
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoveryService",
            return_value=candidate_service,
        ),
    ):
        outcome = DiscoveryExecutionService.run_manufacturer(
            35,
            scan_cidrs=False,
            scan_fqdns=False,
        )

    summary = claim_service.finalize.call_args.args[1]
    assert summary.errors == ["vendor_reconciliation_failed"]
    assert outcome.status == "failed"


@pytest.mark.parametrize("finalize_result", [False, RuntimeError("database unavailable")])
def test_run_manufacturer_contains_finalize_failures(finalize_result: object) -> None:
    manufacturer = SimpleNamespace(code="vendor")
    finalize = Mock()
    if isinstance(finalize_result, Exception):
        finalize.side_effect = finalize_result
    else:
        finalize.return_value = finalize_result
    claim_service = SimpleNamespace(
        claim=Mock(return_value=(manufacturer, SimpleNamespace(pk=3))),
        finalize=finalize,
    )

    with (
        patch(
            "micboard.services.sync.discovery_execution_service.DiscoverySyncClaimService",
            return_value=claim_service,
        ),
        patch("micboard.services.sync.discovery_execution_service.DiscoveryService"),
    ):
        outcome = DiscoveryExecutionService.run_manufacturer(
            35,
            scan_cidrs=False,
            scan_fqdns=False,
        )

    finalize.assert_called_once()
    assert outcome.status == "failed"


@pytest.mark.django_db
def test_run_manufacturer_respects_active_database_claim() -> None:
    """Legacy task entry point cannot reconcile concurrently with an active sync."""
    manufacturer = cast(Manufacturer, ManufacturerFactory())
    DiscoveryJobFactory(
        manufacturer=manufacturer,
        action="sync",
        status="running",
        started_at=timezone.now(),
    )

    with patch(
        "micboard.services.sync.discovery_execution_service.DiscoveryService"
    ) as discovery_service:
        outcome = DiscoveryExecutionService.run_manufacturer(
            manufacturer.pk,
            scan_cidrs=True,
            scan_fqdns=True,
        )

    discovery_service.assert_not_called()
    assert outcome.status == "busy"


def test_task_entry_points_delegate_to_services() -> None:
    result = {"manufacturer": 35, "status": "success"}
    sync_service = SimpleNamespace(run=Mock(return_value=result))
    reconciliation = DiscoveryReconciliationResult(manufacturer=35, status="success")
    with (
        patch.object(
            DiscoveryExecutionService,
            "run_manufacturer",
            return_value=reconciliation,
        ) as run_manufacturer,
        patch.object(DiscoveryExecutionService, "cache_all_candidates") as cache_all,
        patch.object(discovery_tasks, "DiscoverySyncService", return_value=sync_service),
    ):
        reconciliation_result = discovery_tasks.run_manufacturer_discovery_task(35, True, False)
        discovery_tasks.cache_all_discovery_candidates(True, False)
        actual = discovery_tasks.run_discovery_sync_task(
            35,
            ["192.0.2.0/24"],
            ["receiver.example.test"],
            True,
            True,
            16,
        )

    assert actual == result
    assert reconciliation_result == reconciliation.model_dump()
    run_manufacturer.assert_called_once_with(35, scan_cidrs=True, scan_fqdns=False)
    cache_all.assert_called_once_with(scan_cidrs=True, scan_fqdns=False)
    sync_service.run.assert_called_once_with(
        35,
        add_cidrs=["192.0.2.0/24"],
        add_fqdns=["receiver.example.test"],
        scan_cidrs=True,
        scan_fqdns=True,
        max_hosts=16,
    )


def test_busy_reconciliation_requests_one_delayed_retry() -> None:
    outcome = DiscoveryReconciliationResult(manufacturer=36, status="busy")
    with (
        patch.object(DiscoveryExecutionService, "run_manufacturer", return_value=outcome),
        patch.object(discovery_tasks.cache, "add", return_value=True) as cache_add,
        pytest.raises(RetryTask) as exc_info,
    ):
        discovery_tasks.run_manufacturer_discovery_task(36, False, False)

    assert exc_info.value.delay == discovery_tasks.BUSY_RETRY_DELAY_SECONDS
    cache_add.assert_called_once_with(
        "micboard:discovery-retry:36",
        True,
        timeout=discovery_tasks.BUSY_RETRY_COALESCE_SECONDS,
    )


def test_busy_reconciliation_coalesces_duplicate_retry_requests() -> None:
    outcome = DiscoveryReconciliationResult(manufacturer=37, status="busy")
    with (
        patch.object(DiscoveryExecutionService, "run_manufacturer", return_value=outcome),
        patch.object(discovery_tasks.cache, "add", return_value=False),
    ):
        result = discovery_tasks.run_manufacturer_discovery_task(37, True, True)

    assert result == outcome.model_dump()


def test_dispatch_requires_an_id_and_configured_huey() -> None:
    with (
        patch(
            "micboard.utils.dependencies.huey_is_configured",
            return_value=False,
        ) as configured,
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
    ):
        discovery_tasks.dispatch_manufacturer_discovery(0)
        configured.assert_not_called()
        discovery_tasks.dispatch_manufacturer_discovery(36)

    enqueue.assert_not_called()


def test_dispatch_enqueues_and_contains_queue_failures() -> None:
    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
        patch.object(discovery_tasks, "claim_discovery_dispatch", return_value=True) as claim,
        patch.object(discovery_tasks, "release_discovery_dispatch") as release,
    ):
        discovery_tasks.dispatch_manufacturer_discovery(
            37,
            scan_cidrs=False,
            scan_fqdns=True,
        )
        enqueue.side_effect = RuntimeError("queue unavailable")
        discovery_tasks.dispatch_manufacturer_discovery(38)

    assert enqueue.call_args_list == [
        call(discovery_tasks.run_manufacturer_discovery_task, 37, False, True),
        call(discovery_tasks.run_manufacturer_discovery_task, 38, True, True),
    ]
    assert claim.call_count == 2
    release.assert_called_once_with(38, scan_cidrs=True, scan_fqdns=True)


def test_dispatch_coalesces_duplicate_autocommit_requests() -> None:
    manufacturer_id = 987_654_321
    flags = {"scan_cidrs": False, "scan_fqdns": True}
    discovery_tasks.release_discovery_dispatch(manufacturer_id, **flags)
    try:
        with (
            patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
            patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
        ):
            discovery_tasks.dispatch_manufacturer_discovery(manufacturer_id, **flags)
            discovery_tasks.dispatch_manufacturer_discovery(manufacturer_id, **flags)

        enqueue.assert_called_once_with(
            discovery_tasks.run_manufacturer_discovery_task,
            manufacturer_id,
            False,
            True,
        )
    finally:
        discovery_tasks.release_discovery_dispatch(manufacturer_id, **flags)


def test_dispatch_fails_open_when_coalescing_cache_is_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "cache-secret-token\nforged-entry"
    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
        patch(
            "micboard.services.sync.discovery_trigger_service.cache.add",
            side_effect=RuntimeError(secret),
        ),
        caplog.at_level("ERROR"),
    ):
        discovery_tasks.dispatch_manufacturer_discovery(40)

    enqueue.assert_called_once_with(
        discovery_tasks.run_manufacturer_discovery_task,
        40,
        True,
        True,
    )
    assert secret not in caplog.text
    assert "proceeding without coalescing" in caplog.text


def test_failed_enqueue_claim_release_contains_cache_outage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "cache-delete-secret\nforged-entry"
    with (
        patch(
            "micboard.services.sync.discovery_trigger_service.cache.delete",
            side_effect=RuntimeError(secret),
        ),
        caplog.at_level("ERROR"),
    ):
        discovery_tasks.release_discovery_dispatch(
            41,
            scan_cidrs=True,
            scan_fqdns=False,
        )

    assert secret not in caplog.text
    assert "claim could not be released" in caplog.text


def test_discovery_signal_receiver_forwards_payload() -> None:
    with patch.object(discovery_tasks, "dispatch_manufacturer_discovery") as dispatch:
        discovery_tasks._dispatch_discovery_request(
            object(),
            manufacturer_id=39,
            scan_cidrs=False,
            scan_fqdns=True,
            ignored="value",
        )

    dispatch.assert_called_once_with(39, scan_cidrs=False, scan_fqdns=True)
