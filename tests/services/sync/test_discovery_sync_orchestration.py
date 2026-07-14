"""Behavioral coverage for discovery synchronization orchestration and lifecycle."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.models.discovery.registry import DiscoveryJob
from micboard.services.sync.discovery_candidate_source_service import (
    DiscoveryCandidateSourceService,
)
from micboard.services.sync.discovery_claim_service import DiscoverySyncClaimService
from micboard.services.sync.discovery_configuration_service import (
    DiscoveryConfigurationService,
)
from micboard.services.sync.discovery_dtos import (
    DiscoveryCandidatePage,
    DiscoveryScanSourcePage,
    DiscoverySyncSummary,
)
from micboard.services.sync.discovery_sync_service import (
    CLAIM_FAILURE_REASON,
    CONFIG_ENTRIES_INCOMPLETE_REASON,
    FINALIZATION_FAILURE_REASON,
    INVENTORY_SOURCES_INCOMPLETE_REASON,
    MANUFACTURER_INACTIVE_REASON,
    MANUFACTURER_STATUS_CHECK_FAILURE_REASON,
    SCAN_SOURCES_INCOMPLETE_REASON,
    SUPPORTED_MODELS_INCOMPLETE_REASON,
    SYNC_FAILURE_REASON,
    DiscoverySyncService,
)
from tests.factories.discovery import DiscoveryJobFactory, ManufacturerFactory

pytestmark = pytest.mark.django_db


def test_summary_records_terminal_error() -> None:
    summary = DiscoverySyncSummary(manufacturer=40)

    summary.record_error("vendor unavailable")

    assert summary.status == "failed"
    assert summary.errors == ["vendor unavailable"]


def test_run_reports_missing_manufacturer_without_creating_job() -> None:
    result = DiscoverySyncService().run(999_999)

    assert result == {
        "manufacturer": 999_999,
        "status": "failed",
        "created_receivers": 0,
        "missing_ips_submitted": 0,
        "scanned_ips_submitted": 0,
        "errors": ["Manufacturer 999999 not found"],
    }
    assert not DiscoveryJob.objects.exists()


def test_run_reports_job_creation_failure() -> None:
    manufacturer = ManufacturerFactory()
    with patch(
        "micboard.services.sync.discovery_claim_service.DiscoveryJob.objects.create",
        side_effect=RuntimeError("database unavailable"),
    ):
        result = DiscoverySyncService().run(manufacturer.pk)

    assert result["status"] == "failed"
    assert result["errors"] == [CLAIM_FAILURE_REASON]


def test_run_returns_stable_failure_when_manufacturer_sync_is_already_running() -> None:
    manufacturer = ManufacturerFactory()
    active_job = DiscoveryJobFactory(
        manufacturer=manufacturer,
        status="running",
        started_at=timezone.now(),
    )
    service = DiscoverySyncService()
    with (
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance"
        ) as get_plugin,
    ):
        result = service.run(manufacturer.pk)

    assert result == {
        "manufacturer": manufacturer.pk,
        "status": "failed",
        "created_receivers": 0,
        "missing_ips_submitted": 0,
        "scanned_ips_submitted": 0,
        "errors": [f"Discovery synchronization already running for manufacturer {manufacturer.pk}"],
    }
    assert list(DiscoveryJob.objects.all()) == [active_job]
    get_plugin.assert_not_called()


def test_run_reports_claim_backend_failure_without_starting_work() -> None:
    manufacturer = ManufacturerFactory()
    service = DiscoverySyncService()
    with (
        patch.object(
            service.claim_service,
            "claim",
            side_effect=RuntimeError("database unavailable"),
        ),
        patch.object(service, "_run_claimed") as run_claimed,
    ):
        result = service.run(manufacturer.pk)

    assert result["status"] == "failed"
    assert result["errors"] == [CLAIM_FAILURE_REASON]
    run_claimed.assert_not_called()


def test_run_coordinates_services_and_finalizes_successful_job() -> None:
    manufacturer = ManufacturerFactory()
    device_client = Mock()
    plugin = SimpleNamespace(get_client=Mock(return_value=SimpleNamespace(devices=device_client)))
    service = DiscoverySyncService()

    events: list[str] = []

    def submit(*_args, **_kwargs) -> None:
        events.append("push")

    def poll(_manufacturer, _plugin, summary):
        events.append("pull")
        summary.created_receivers += 2
        return [{"ipAddress": "192.0.2.41"}, {"ipv4": "192.0.2.42"}]

    with (
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch.object(DiscoveryConfigurationService, "add_entries") as add_config,
        patch.object(
            DiscoveryConfigurationService,
            "persist_supported_models",
            return_value=True,
        ) as persist_models,
        patch(
            "micboard.services.sync.discovery_sync_service.DiscoveryQueueService.poll_and_persist",
            side_effect=poll,
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "configured_scan_sources",
            return_value=DiscoveryScanSourcePage(
                cidrs=["192.0.2.0/24"],
                fqdns=["receiver.example.test"],
            ),
        ) as configured_sources,
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_inventory_candidates",
            return_value=DiscoveryCandidatePage(candidates=["192.0.2.41"]),
        ) as collect_inventory,
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_scanned_candidates",
            return_value=DiscoveryCandidatePage(candidates=["192.0.2.42"]),
        ) as collect_scanned,
        patch.object(service, "submit_candidates", side_effect=submit) as submit_candidates,
        patch.object(service, "broadcast_results") as broadcast,
    ):
        result = service.run(
            manufacturer.pk,
            add_cidrs=["198.51.100.0/24"],
            add_fqdns=["new.example.test"],
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=16,
        )

    assert result["status"] == "success"
    assert result["created_receivers"] == 2
    add_config.assert_called_once_with(
        manufacturer,
        cidrs=["198.51.100.0/24"],
        fqdns=["new.example.test"],
    )
    persist_models.assert_called_once_with(manufacturer, device_client)
    collect_inventory.assert_called_once_with(manufacturer, limit=16)
    configured_sources.assert_called_once_with(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=True,
        limit=15,
    )
    collect_scanned.assert_called_once_with(
        cidrs=["192.0.2.0/24"],
        fqdns=["receiver.example.test"],
        scan_cidrs=True,
        scan_fqdns=True,
        max_hosts=15,
        source_order=[],
    )
    assert submit_candidates.call_args.kwargs["missing_ips"] == ["192.0.2.41"]
    assert submit_candidates.call_args.kwargs["scanned_ips"] == ["192.0.2.42"]
    assert events == ["push", "pull"]
    broadcast.assert_called_once_with(manufacturer)
    job = DiscoveryJob.objects.get(manufacturer=manufacturer)
    assert job.status == "success"
    assert job.finished_at is not None


def test_run_reports_incomplete_local_pages_after_safe_bounded_submission() -> None:
    manufacturer = ManufacturerFactory()
    plugin = SimpleNamespace(
        get_client=Mock(return_value=SimpleNamespace(devices=None)),
    )
    service = DiscoverySyncService()

    with (
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_inventory_candidates",
            return_value=DiscoveryCandidatePage(
                candidates=["192.0.2.41"],
                sources_complete=False,
            ),
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "configured_scan_sources",
            return_value=DiscoveryScanSourcePage(
                cidrs=["192.0.2.0/24"],
                sources_complete=False,
            ),
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_scanned_candidates",
            return_value=DiscoveryCandidatePage(candidates=["192.0.2.42"]),
        ),
        patch.object(service, "submit_candidates") as submit,
        patch(
            "micboard.services.sync.discovery_sync_service.DiscoveryQueueService.poll_and_persist",
            return_value=[],
        ),
        patch.object(service, "broadcast_results"),
    ):
        result = service.run(
            manufacturer.pk,
            scan_cidrs=True,
            max_hosts=2,
        )

    assert result["status"] == "failed"
    assert result["errors"] == [
        INVENTORY_SOURCES_INCOMPLETE_REASON,
        SCAN_SOURCES_INCOMPLETE_REASON,
    ]
    assert submit.call_args.kwargs["missing_ips"] == ["192.0.2.41"]
    assert submit.call_args.kwargs["scanned_ips"] == ["192.0.2.42"]
    job = DiscoveryJob.objects.get(manufacturer=manufacturer)
    assert job.status == "failed"


def test_run_reports_incomplete_scan_expansion_after_safe_submission() -> None:
    manufacturer = ManufacturerFactory()
    plugin = SimpleNamespace(
        get_client=Mock(return_value=SimpleNamespace(devices=None)),
    )
    service = DiscoverySyncService()

    with (
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_inventory_candidates",
            return_value=DiscoveryCandidatePage(),
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "configured_scan_sources",
            return_value=DiscoveryScanSourcePage(
                cidrs=["192.0.2.0/24"],
                source_order=["cidrs"],
            ),
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_scanned_candidates",
            return_value=DiscoveryCandidatePage(
                candidates=["192.0.2.1"],
                sources_complete=False,
            ),
        ),
        patch.object(service, "submit_candidates") as submit,
        patch(
            "micboard.services.sync.discovery_sync_service.DiscoveryQueueService.poll_and_persist",
            return_value=[],
        ),
        patch.object(service, "broadcast_results"),
    ):
        result = service.run(
            manufacturer.pk,
            scan_cidrs=True,
            max_hosts=2,
        )

    assert result["status"] == "failed"
    assert result["errors"] == [SCAN_SOURCES_INCOMPLETE_REASON]
    assert submit.call_args.kwargs["scanned_ips"] == ["192.0.2.1"]


def test_run_marks_oversized_supported_model_snapshot_incomplete() -> None:
    manufacturer = ManufacturerFactory()
    plugin = SimpleNamespace(
        get_client=Mock(return_value=SimpleNamespace(devices=object())),
    )
    service = DiscoverySyncService()

    with (
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch.object(
            DiscoveryConfigurationService,
            "persist_supported_models",
            return_value=False,
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_inventory_candidates",
            return_value=DiscoveryCandidatePage(),
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "configured_scan_sources",
            return_value=DiscoveryScanSourcePage(),
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_scanned_candidates",
            return_value=DiscoveryCandidatePage(),
        ),
        patch.object(service, "submit_candidates"),
        patch(
            "micboard.services.sync.discovery_sync_service.DiscoveryQueueService.poll_and_persist",
            return_value=[],
        ),
        patch.object(service, "broadcast_results"),
    ):
        result = service.run(manufacturer.pk)

    assert result["status"] == "failed"
    assert result["errors"] == [SUPPORTED_MODELS_INCOMPLETE_REASON]


def test_run_marks_invalid_configuration_input_incomplete() -> None:
    manufacturer = ManufacturerFactory()
    service = DiscoverySyncService()

    with (
        patch.object(DiscoveryConfigurationService, "add_entries", return_value=False),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_inventory_candidates",
            side_effect=RuntimeError,
        ),
    ):
        result = service.run(manufacturer.pk)

    assert result["status"] == "failed"
    assert result["errors"] == [CONFIG_ENTRIES_INCOMPLETE_REASON, SYNC_FAILURE_REASON]


def test_run_clamps_caller_controlled_candidate_limit() -> None:
    manufacturer = ManufacturerFactory()
    plugin = SimpleNamespace(
        get_client=Mock(return_value=SimpleNamespace(devices=None)),
    )
    service = DiscoverySyncService()

    with (
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_inventory_candidates",
            return_value=DiscoveryCandidatePage(),
        ) as inventory,
        patch.object(
            DiscoveryCandidateSourceService,
            "configured_scan_sources",
            return_value=DiscoveryScanSourcePage(),
        ) as sources,
        patch.object(
            DiscoveryCandidateSourceService,
            "collect_scanned_candidates",
            return_value=DiscoveryCandidatePage(),
        ) as scanned,
        patch.object(service, "submit_candidates") as submit,
        patch(
            "micboard.services.sync.discovery_sync_service.DiscoveryQueueService.poll_and_persist"
        ),
        patch.object(service, "broadcast_results"),
    ):
        result = service.run(
            manufacturer.pk,
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=MAX_DISCOVERY_CANDIDATES * 100,
        )

    assert result["status"] == "success"
    inventory.assert_called_once_with(manufacturer, limit=MAX_DISCOVERY_CANDIDATES)
    sources.assert_called_once_with(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=True,
        limit=MAX_DISCOVERY_CANDIDATES,
    )
    scanned.assert_called_once_with(
        cidrs=[],
        fqdns=[],
        scan_cidrs=True,
        scan_fqdns=True,
        max_hosts=MAX_DISCOVERY_CANDIDATES,
        source_order=[],
    )
    assert submit.call_args.kwargs["missing_ips"] == []
    assert submit.call_args.kwargs["scanned_ips"] == []


def test_run_finalizes_failure_and_does_not_broadcast_partial_state() -> None:
    manufacturer = ManufacturerFactory()
    service = DiscoverySyncService()
    with (
        patch.object(
            DiscoveryConfigurationService,
            "add_entries",
            side_effect=RuntimeError("invalid config"),
        ),
        patch.object(service, "broadcast_results") as broadcast,
    ):
        result = service.run(manufacturer.pk)

    assert result["status"] == "failed"
    assert result["errors"] == [SYNC_FAILURE_REASON]
    broadcast.assert_not_called()
    job = DiscoveryJob.objects.get(manufacturer=manufacturer)
    assert job.status == "failed"
    assert job.note == SYNC_FAILURE_REASON
    assert job.finished_at is not None


def test_run_does_not_expose_or_persist_raw_exception_details() -> None:
    manufacturer = ManufacturerFactory()
    secret = "vendor-token-SENTINEL\nforged-log-line"
    service = DiscoverySyncService()

    with patch.object(
        DiscoveryConfigurationService,
        "add_entries",
        side_effect=RuntimeError(secret),
    ):
        result = service.run(manufacturer.pk)

    job = DiscoveryJob.objects.get(manufacturer=manufacturer)
    assert result["errors"] == [SYNC_FAILURE_REASON]
    assert job.note == SYNC_FAILURE_REASON
    assert "SENTINEL" not in str(result)
    assert "SENTINEL" not in job.note


def test_run_finalizes_without_vendor_work_after_post_claim_deactivation() -> None:
    """A claim owner rechecks activation before loading any vendor plugin."""
    manufacturer = ManufacturerFactory(is_active=False)
    job = DiscoveryJobFactory(manufacturer=manufacturer, status="running")
    claim_service = Mock(spec=DiscoverySyncClaimService)
    claim_service.claim.return_value = (manufacturer, job)
    claim_service.finalize.return_value = True
    service = DiscoverySyncService(claim_service=claim_service)

    with (
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance"
        ) as get_plugin,
        patch.object(service, "broadcast_results") as broadcast,
    ):
        result = service.run(manufacturer.pk)

    get_plugin.assert_not_called()
    broadcast.assert_not_called()
    summary = claim_service.finalize.call_args.args[1]
    assert summary.errors == [MANUFACTURER_INACTIVE_REASON]
    assert result["errors"] == [MANUFACTURER_INACTIVE_REASON]


def test_run_finalizes_when_post_claim_activation_check_fails() -> None:
    """An activation-query outage cannot strand the claim or reach a vendor plugin."""
    manufacturer = ManufacturerFactory()
    job = DiscoveryJobFactory(manufacturer=manufacturer, status="running")
    claim_service = Mock(spec=DiscoverySyncClaimService)
    claim_service.claim.return_value = (manufacturer, job)
    claim_service.finalize.return_value = True
    service = DiscoverySyncService(claim_service=claim_service)

    with (
        patch(
            "micboard.services.sync.discovery_sync_service.ManufacturerActivationService.is_active",
            side_effect=RuntimeError("database unavailable"),
        ),
        patch(
            "micboard.services.sync.discovery_sync_service.get_manufacturer_plugin_instance"
        ) as get_plugin,
    ):
        result = service.run(manufacturer.pk)

    get_plugin.assert_not_called()
    summary = claim_service.finalize.call_args.args[1]
    assert summary.errors == [MANUFACTURER_STATUS_CHECK_FAILURE_REASON]
    assert result["errors"] == [MANUFACTURER_STATUS_CHECK_FAILURE_REASON]


def test_run_reports_finalization_failure_without_broadcasting() -> None:
    manufacturer = ManufacturerFactory()
    job = DiscoveryJobFactory(manufacturer=manufacturer, status="running")
    claim_service = Mock(spec=DiscoverySyncClaimService)
    claim_service.claim.return_value = (manufacturer, job)
    claim_service.finalize.side_effect = RuntimeError("finalize unavailable")
    service = DiscoverySyncService(claim_service=claim_service)

    with (
        patch.object(
            DiscoveryConfigurationService,
            "add_entries",
            side_effect=RuntimeError("invalid config"),
        ),
        patch.object(service, "broadcast_results") as broadcast,
    ):
        result = service.run(manufacturer.pk)

    assert result["errors"] == [SYNC_FAILURE_REASON, FINALIZATION_FAILURE_REASON]
    broadcast.assert_not_called()


def test_run_does_not_publish_after_losing_its_database_claim() -> None:
    manufacturer = ManufacturerFactory()
    job = DiscoveryJobFactory(manufacturer=manufacturer, status="running")
    claim_service = Mock(spec=DiscoverySyncClaimService)
    claim_service.claim.return_value = (manufacturer, job)
    claim_service.finalize.return_value = False
    service = DiscoverySyncService(claim_service=claim_service)

    with (
        patch.object(
            DiscoveryConfigurationService,
            "add_entries",
            side_effect=RuntimeError("invalid config"),
        ),
        patch.object(service, "broadcast_results") as broadcast,
    ):
        result = service.run(manufacturer.pk)

    assert result["errors"] == [
        SYNC_FAILURE_REASON,
        "Discovery synchronization claim expired before finalization",
    ]
    broadcast.assert_not_called()
