"""Discovery candidate cache publication contracts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Literal
from unittest.mock import Mock, call, patch

import pytest

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.services.sync.discovery_dtos import DiscoveryReconciliationResult
from micboard.services.sync.discovery_execution_service import DiscoveryExecutionService


@pytest.fixture(autouse=True)
def active_manufacturer_boundary(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Keep unit doubles active unless a test exercises post-reconciliation revocation."""
    activation_check = Mock(return_value=True)
    monkeypatch.setattr(
        "micboard.services.sync.discovery_execution_service."
        "ManufacturerActivationService.is_active",
        activation_check,
    )
    return activation_check


def test_cache_all_candidates_isolates_manufacturer_failures() -> None:
    first = SimpleNamespace(pk=1, code="first")
    second = SimpleNamespace(pk=2, code="second")
    first_plugin = SimpleNamespace(get_discovery_ips=Mock(return_value=["192.0.2.34"]))
    cache = Mock()
    with (
        patch(
            "micboard.services.sync.discovery_execution_service.Manufacturer.objects.order_by",
            return_value=[first, second],
        ),
        patch.object(
            DiscoveryExecutionService,
            "run_manufacturer",
            side_effect=[
                DiscoveryReconciliationResult(manufacturer=1, status="success"),
                DiscoveryReconciliationResult(manufacturer=2, status="success"),
            ],
        ) as run,
        patch(
            "micboard.services.sync.discovery_execution_service.get_manufacturer_plugin_instance",
            side_effect=[first_plugin, RuntimeError("plugin unavailable")],
        ),
        patch("micboard.services.sync.discovery_execution_service.cache", cache),
    ):
        DiscoveryExecutionService.cache_all_candidates(
            scan_cidrs=True,
            scan_fqdns=False,
        )

    assert run.call_args_list == [
        call(1, scan_cidrs=True, scan_fqdns=False),
        call(2, scan_cidrs=True, scan_fqdns=False),
    ]
    cache.set.assert_called_once_with(
        "discovery_candidates_first_1_0",
        {"first": {"ips": ["192.0.2.34"]}},
        timeout=300,
    )


@pytest.mark.parametrize("status", ["busy", "failed"])
def test_cache_all_candidates_skips_non_successful_reconciliation(
    status: Literal["busy", "failed"],
) -> None:
    manufacturer = SimpleNamespace(pk=4, code="vendor")
    with (
        patch(
            "micboard.services.sync.discovery_execution_service.Manufacturer.objects.order_by",
            return_value=[manufacturer],
        ),
        patch.object(
            DiscoveryExecutionService,
            "run_manufacturer",
            return_value=DiscoveryReconciliationResult(
                manufacturer=4,
                status=status,
            ),
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.get_manufacturer_plugin_instance"
        ) as get_plugin,
        patch("micboard.services.sync.discovery_execution_service.cache") as cache,
    ):
        DiscoveryExecutionService.cache_all_candidates(
            scan_cidrs=False,
            scan_fqdns=False,
        )

    get_plugin.assert_not_called()
    cache.set.assert_not_called()


def test_cache_all_candidates_rechecks_activation_after_reconciliation(
    active_manufacturer_boundary: Mock,
) -> None:
    """Deactivation after reconciliation prevents the follow-up vendor cache request."""
    manufacturer = SimpleNamespace(pk=7, code="vendor")

    def deactivate_after_reconciliation(*_args, **_kwargs) -> DiscoveryReconciliationResult:
        active_manufacturer_boundary.return_value = False
        return DiscoveryReconciliationResult(manufacturer=7, status="success")

    with (
        patch(
            "micboard.services.sync.discovery_execution_service.Manufacturer.objects.order_by",
            return_value=[manufacturer],
        ),
        patch.object(
            DiscoveryExecutionService,
            "run_manufacturer",
            side_effect=deactivate_after_reconciliation,
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.get_manufacturer_plugin_instance"
        ) as get_plugin,
        patch("micboard.services.sync.discovery_execution_service.cache") as cache,
    ):
        DiscoveryExecutionService.cache_all_candidates(
            scan_cidrs=False,
            scan_fqdns=False,
        )

    active_manufacturer_boundary.assert_called_once_with(7)
    get_plugin.assert_not_called()
    cache.set.assert_not_called()


def test_cache_all_candidates_rejects_oversized_remote_state() -> None:
    manufacturer = SimpleNamespace(pk=5, code="vendor")
    plugin = SimpleNamespace(
        get_discovery_ips=Mock(return_value=["192.0.2.1"] * (MAX_DISCOVERY_CANDIDATES + 1))
    )
    with (
        patch(
            "micboard.services.sync.discovery_execution_service.Manufacturer.objects.order_by",
            return_value=[manufacturer],
        ),
        patch.object(
            DiscoveryExecutionService,
            "run_manufacturer",
            return_value=DiscoveryReconciliationResult(manufacturer=5, status="success"),
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch("micboard.services.sync.discovery_execution_service.cache") as cache,
    ):
        DiscoveryExecutionService.cache_all_candidates(
            scan_cidrs=False,
            scan_fqdns=False,
        )

    cache.set.assert_not_called()


def test_cache_all_candidates_bounds_invalid_vendor_iterable_before_validation() -> None:
    manufacturer = SimpleNamespace(pk=6, code="vendor")
    consumed = 0

    def remote_items():
        nonlocal consumed
        for _index in range(MAX_DISCOVERY_CANDIDATES + 2):
            consumed += 1
            yield object()

    plugin = SimpleNamespace(get_discovery_ips=Mock(return_value=remote_items()))
    with (
        patch(
            "micboard.services.sync.discovery_execution_service.Manufacturer.objects.order_by",
            return_value=[manufacturer],
        ),
        patch.object(
            DiscoveryExecutionService,
            "run_manufacturer",
            return_value=DiscoveryReconciliationResult(manufacturer=6, status="success"),
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.get_manufacturer_plugin_instance",
            return_value=plugin,
        ),
        patch("micboard.services.sync.discovery_execution_service.cache") as cache,
    ):
        DiscoveryExecutionService.cache_all_candidates(
            scan_cidrs=False,
            scan_fqdns=False,
        )

    assert consumed == MAX_DISCOVERY_CANDIDATES + 1
    cache.set.assert_not_called()


def test_cache_all_candidates_bounds_manufacturer_projection() -> None:
    manufacturers = [SimpleNamespace(pk=index, code=f"vendor-{index}") for index in range(3)]
    with (
        patch(
            "micboard.services.sync.discovery_execution_service.MAX_DISCOVERY_CANDIDATES",
            2,
        ),
        patch(
            "micboard.services.sync.discovery_execution_service.Manufacturer.objects.order_by",
            return_value=manufacturers,
        ),
        patch.object(
            DiscoveryExecutionService,
            "run_manufacturer",
            return_value=DiscoveryReconciliationResult(
                manufacturer=1,
                status="failed",
            ),
        ) as run,
    ):
        DiscoveryExecutionService.cache_all_candidates(
            scan_cidrs=False,
            scan_fqdns=False,
        )

    assert run.call_count == 2
