"""Discovery task dispatch and bounded batch-submission contracts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.services.sync.discovery_service import DiscoveryService
from micboard.tasks.sync.discovery import dispatch_manufacturer_discovery
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_trigger_discovery_ignores_empty_manufacturer_pk() -> None:
    with (
        patch("micboard.utils.dependencies.huey_is_configured") as configured,
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
    ):
        dispatch_manufacturer_discovery(0)

    configured.assert_not_called()
    enqueue.assert_not_called()


def test_trigger_discovery_enqueues_native_huey_task() -> None:
    manufacturer = ManufacturerFactory()

    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
        patch("micboard.tasks.sync.discovery.run_manufacturer_discovery_task") as discovery_task,
        patch(
            "micboard.tasks.sync.discovery.claim_discovery_dispatch",
            return_value=True,
        ),
    ):
        dispatch_manufacturer_discovery(
            manufacturer.pk,
            scan_cidrs=False,
            scan_fqdns=True,
        )

    enqueue.assert_called_once_with(discovery_task, manufacturer.pk, False, True)


def test_trigger_discovery_skips_when_queue_is_unconfigured() -> None:
    manufacturer = ManufacturerFactory()

    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=False),
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
        patch("micboard.tasks.sync.discovery.run_manufacturer_discovery_task") as discovery_task,
    ):
        dispatch_manufacturer_discovery(manufacturer.pk)

    enqueue.assert_not_called()
    discovery_task.assert_not_called()


def test_trigger_discovery_does_not_run_inline_after_enqueue_failure() -> None:
    manufacturer = ManufacturerFactory()

    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch(
            "micboard.utils.dependencies.enqueue_huey_task",
            side_effect=RuntimeError("queue unavailable"),
        ),
        patch("micboard.tasks.sync.discovery.run_manufacturer_discovery_task") as discovery_task,
        patch(
            "micboard.tasks.sync.discovery.claim_discovery_dispatch",
            return_value=True,
        ),
        patch("micboard.tasks.sync.discovery.release_discovery_dispatch") as release,
    ):
        dispatch_manufacturer_discovery(
            manufacturer.pk,
            scan_cidrs=False,
            scan_fqdns=False,
        )

    discovery_task.assert_not_called()
    release.assert_called_once_with(
        manufacturer.pk,
        scan_cidrs=False,
        scan_fqdns=False,
    )


def test_trigger_discovery_contains_missing_manufacturer() -> None:
    with patch("micboard.utils.dependencies.huey_is_configured", return_value=False):
        dispatch_manufacturer_discovery(999_999)


def test_batch_candidate_submission_resolves_plugin_when_not_injected() -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.add_discovery_ips.return_value = True
    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ) as get_plugin:
        result = DiscoveryService().add_discovery_candidates(manufacturer, ["192.0.2.80"])

    get_plugin.assert_called_once_with(manufacturer)
    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.80"])
    assert result.submitted_ips == ["192.0.2.80"]
    assert result.failed_ips == []


def test_batch_candidate_submission_canonicalizes_and_rejects_invalid_addresses() -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.add_discovery_ips.return_value = True
    with patch.object(DiscoveryService, "_get_conflicting_ips", return_value=set()):
        result = DiscoveryService().add_discovery_candidates(
            manufacturer,
            ["2001:0db8::1", "invalid", "2001:db8::1"],
            plugin=plugin,
        )

    plugin.add_discovery_ips.assert_called_once_with(["2001:db8::1"])
    assert result.submitted_ips == ["2001:db8::1"]
    assert result.rejected_count == 1


def test_batch_candidate_submission_preserves_attribution_across_chunks(
    django_assert_num_queries,
) -> None:
    manufacturer = ManufacturerFactory()
    other = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=other, ip="192.0.2.82")
    plugin = MagicMock()
    plugin.add_discovery_ips.side_effect = [True, False]
    candidates = [
        "192.0.2.80",
        "192.0.2.81",
        "192.0.2.82",
        "192.0.2.83",
        "192.0.2.84",
    ]

    with django_assert_num_queries(1):
        result = DiscoveryService().add_discovery_candidates(
            manufacturer,
            candidates,
            plugin=plugin,
            batch_size=2,
        )

    assert [mock_call.args[0] for mock_call in plugin.add_discovery_ips.call_args_list] == [
        ["192.0.2.80", "192.0.2.81"],
        ["192.0.2.83", "192.0.2.84"],
    ]
    assert result.submitted_ips == ["192.0.2.80", "192.0.2.81"]
    assert result.failed_ips == ["192.0.2.82", "192.0.2.83", "192.0.2.84"]


def test_batch_candidate_submission_rejects_invalid_batch_size() -> None:
    manufacturer = ManufacturerFactory()

    with pytest.raises(ValueError, match="batch_size must be greater than zero"):
        DiscoveryService().add_discovery_candidates(
            manufacturer,
            ["192.0.2.80"],
            batch_size=0,
        )


def test_batch_candidate_submission_bounds_arbitrary_iterable_before_query(
    django_assert_num_queries,
) -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    consumed = 0

    def excessive_candidates():
        nonlocal consumed
        for index in range(MAX_DISCOVERY_CANDIDATES + 2):
            consumed += 1
            yield f"candidate-{index}"

    with (
        django_assert_num_queries(0),
        pytest.raises(
            ValueError,
            match=f"candidate count exceeds hard limit of {MAX_DISCOVERY_CANDIDATES}",
        ),
    ):
        DiscoveryService().add_discovery_candidates(
            manufacturer,
            excessive_candidates(),
            plugin=plugin,
        )

    assert consumed == MAX_DISCOVERY_CANDIDATES + 1
    plugin.add_discovery_ips.assert_not_called()
