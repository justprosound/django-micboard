"""Coverage for discovery source expansion, candidate submission, and publication."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from micboard.services.sync.discovery_dtos import DiscoverySyncSummary
from micboard.services.sync.discovery_sync_service import DiscoverySyncService
from tests.factories.discovery import (
    DiscoveredDeviceFactory,
    DiscoveryCIDRFactory,
    DiscoveryFQDNFactory,
    ManufacturerFactory,
)
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_configured_scan_sources_are_scoped_to_manufacturer() -> None:
    manufacturer = ManufacturerFactory()
    other = ManufacturerFactory()
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="192.0.2.0/30")
    DiscoveryCIDRFactory(manufacturer=other, cidr="198.51.100.0/30")
    DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn="receiver.example.test")
    DiscoveryFQDNFactory(manufacturer=other, fqdn="other.example.test")

    page = DiscoverySyncService.configured_scan_sources(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=True,
        limit=8,
    )
    assert page.cidrs == ["192.0.2.0/30"]
    assert page.fqdns == ["receiver.example.test"]
    assert page.sources_complete is True


def test_configured_scan_sources_bounds_materialization_and_skips_disabled_sources() -> None:
    manufacturer = ManufacturerFactory()
    for index in range(3):
        DiscoveryCIDRFactory(manufacturer=manufacturer, cidr=f"192.0.2.{index}/32")
        DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn=f"receiver-{index}.example.test")

    bounded = DiscoverySyncService.configured_scan_sources(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=False,
        limit=2,
    )
    assert bounded.cidrs == ["192.0.2.0/32", "192.0.2.1/32"]
    assert bounded.fqdns == []
    assert bounded.sources_complete is False
    empty = DiscoverySyncService.configured_scan_sources(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=True,
        limit=0,
    )
    assert empty.cidrs == []
    assert empty.fqdns == []
    assert empty.sources_complete is False

    disabled = DiscoverySyncService.configured_scan_sources(
        manufacturer,
        scan_cidrs=False,
        scan_fqdns=False,
        limit=2,
    )
    assert disabled.cidrs == []
    assert disabled.fqdns == []
    assert disabled.source_order == []
    assert disabled.sources_complete is True


def test_configured_scan_sources_rotate_across_types_and_wrap() -> None:
    manufacturer = ManufacturerFactory()
    cidrs = [
        DiscoveryCIDRFactory(manufacturer=manufacturer, cidr=f"192.0.2.{index}/32")
        for index in range(3)
    ]
    fqdns = [
        DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn=f"receiver-{index}.example.test")
        for index in range(3)
    ]

    pages = [
        DiscoverySyncService.configured_scan_sources(
            manufacturer,
            scan_cidrs=True,
            scan_fqdns=True,
            limit=2,
        )
        for _index in range(4)
    ]

    assert [(page.cidrs, page.fqdns) for page in pages] == [
        ([cidrs[0].cidr], [fqdns[0].fqdn]),
        ([cidrs[1].cidr], [fqdns[1].fqdn]),
        ([cidrs[2].cidr], [fqdns[2].fqdn]),
        ([cidrs[0].cidr], [fqdns[0].fqdn]),
    ]
    assert not any(page.sources_complete for page in pages)


def test_collect_inventory_candidates_is_scoped_and_deduplicated() -> None:
    manufacturer = ManufacturerFactory()
    other = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.53")
    DiscoveredDeviceFactory(manufacturer=manufacturer, ip="192.0.2.53")
    DiscoveredDeviceFactory(manufacturer=manufacturer, ip="192.0.2.54")
    DiscoveredDeviceFactory(manufacturer=other, ip="192.0.2.56")

    page = DiscoverySyncService.collect_inventory_candidates(manufacturer)
    assert page.candidates == [
        "192.0.2.53",
        "192.0.2.54",
    ]
    assert page.sources_complete is True


def test_collect_inventory_candidates_honors_aggregate_limit() -> None:
    manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.55")
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.56")
    DiscoveredDeviceFactory(manufacturer=manufacturer, ip="192.0.2.57")

    first = DiscoverySyncService.collect_inventory_candidates(manufacturer, limit=2)
    second = DiscoverySyncService.collect_inventory_candidates(manufacturer, limit=2)

    assert first.candidates == ["192.0.2.55", "192.0.2.57"]
    assert second.candidates == ["192.0.2.56", "192.0.2.57"]
    assert first.sources_complete is False
    assert second.sources_complete is False
    zero = DiscoverySyncService.collect_inventory_candidates(manufacturer, limit=0)
    assert zero.candidates == []
    assert zero.sources_complete is False


def test_inventory_shared_cap_rotates_source_priority_and_each_page_wraps() -> None:
    manufacturer = ManufacturerFactory()
    configured = [
        WirelessChassisFactory(manufacturer=manufacturer, ip=f"192.0.2.{index}")
        for index in range(60, 63)
    ]
    staged = [
        DiscoveredDeviceFactory(manufacturer=manufacturer, ip=f"192.0.2.{index}")
        for index in range(70, 73)
    ]

    one_item_pages = [
        DiscoverySyncService.collect_inventory_candidates(manufacturer, limit=1)
        for _index in range(2)
    ]
    later_pages = [
        DiscoverySyncService.collect_inventory_candidates(manufacturer, limit=2)
        for _index in range(4)
    ]

    assert one_item_pages[0].candidates == [configured[0].ip]
    assert one_item_pages[1].candidates == [staged[0].ip]
    assert later_pages[0].candidates == [configured[1].ip, staged[1].ip]
    assert later_pages[1].candidates == [configured[2].ip, staged[2].ip]
    assert later_pages[2].candidates == [configured[0].ip, staged[0].ip]
    assert later_pages[3].candidates == later_pages[0].candidates
    assert not any(page.sources_complete for page in [*one_item_pages, *later_pages])


def test_inventory_pagination_fails_open_during_cache_outage(caplog) -> None:
    manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.80")
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.81")
    DiscoveredDeviceFactory(manufacturer=manufacturer, ip="192.0.2.82")
    secret = "cache-credential"

    with (
        patch(
            "micboard.services.sync.discovery_source_cursor_service.cache.get",
            side_effect=RuntimeError(secret),
        ),
        patch(
            "micboard.services.sync.discovery_source_cursor_service.cache.set",
            side_effect=RuntimeError(secret),
        ),
    ):
        page = DiscoverySyncService.collect_inventory_candidates(manufacturer, limit=2)

    assert page.candidates == ["192.0.2.80", "192.0.2.82"]
    assert page.sources_complete is False
    assert secret not in caplog.text


def test_inventory_pagination_resets_invalid_cursor_and_handles_empty_sources() -> None:
    manufacturer = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.90")

    with patch(
        "micboard.services.sync.discovery_source_cursor_service.cache.get",
        return_value=True,
    ):
        page = DiscoverySyncService.collect_inventory_candidates(manufacturer, limit=2)

    assert page.candidates == ["192.0.2.90"]
    assert page.sources_complete is True

    empty_manufacturer = ManufacturerFactory()
    empty_page = DiscoverySyncService.collect_inventory_candidates(empty_manufacturer, limit=2)
    assert empty_page.candidates == []
    assert empty_page.sources_complete is True


def test_submit_candidates_deduplicates_one_batch_and_preserves_source_counts(
    django_assert_num_queries,
) -> None:
    manufacturer = ManufacturerFactory()
    other = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=other, ip="192.0.2.63")
    plugin = Mock()
    plugin.add_discovery_ips.return_value = True
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk)

    with django_assert_num_queries(1):
        DiscoverySyncService().submit_candidates(
            manufacturer,
            missing_ips=["192.0.2.60", "192.0.2.61", "192.0.2.60"],
            scanned_ips=["192.0.2.61", "192.0.2.62", "192.0.2.62", "192.0.2.63"],
            plugin=plugin,
            summary=summary,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.60", "192.0.2.61", "192.0.2.62"])
    assert summary.missing_ips_submitted == 2
    assert summary.scanned_ips_submitted == 1
    assert summary.errors == ["Failed to submit 1 scanned discovery candidate"]


def test_submit_candidates_records_batch_failure_by_original_source() -> None:
    manufacturer = ManufacturerFactory()
    plugin = Mock()
    plugin.add_discovery_ips.return_value = False
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk)

    DiscoverySyncService().submit_candidates(
        manufacturer,
        missing_ips=["192.0.2.70"],
        scanned_ips=["192.0.2.71"],
        plugin=plugin,
        summary=summary,
    )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.70", "192.0.2.71"])
    assert summary.missing_ips_submitted == 0
    assert summary.scanned_ips_submitted == 0
    assert summary.errors == [
        "Failed to submit 1 missing discovery candidate",
        "Failed to submit 1 scanned discovery candidate",
    ]


def test_submit_candidates_rejects_all_cross_manufacturer_conflicts_without_api_call() -> None:
    manufacturer = ManufacturerFactory()
    other = ManufacturerFactory()
    WirelessChassisFactory(manufacturer=other, ip="192.0.2.72")
    plugin = Mock()
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk)

    DiscoverySyncService().submit_candidates(
        manufacturer,
        missing_ips=["192.0.2.72"],
        scanned_ips=[],
        plugin=plugin,
        summary=summary,
    )

    plugin.add_discovery_ips.assert_not_called()
    assert summary.missing_ips_submitted == 0
    assert summary.errors == ["Failed to submit 1 missing discovery candidate"]


def test_submit_candidates_handles_empty_input_without_query_or_api_call(
    django_assert_num_queries,
) -> None:
    manufacturer = ManufacturerFactory()
    plugin = Mock()
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk)

    with django_assert_num_queries(0):
        DiscoverySyncService().submit_candidates(
            manufacturer,
            missing_ips=[],
            scanned_ips=[],
            plugin=plugin,
            summary=summary,
        )

    plugin.add_discovery_ips.assert_not_called()
    assert summary.missing_ips_submitted == 0
    assert summary.scanned_ips_submitted == 0
    assert summary.errors == []


def test_submit_candidates_default_cap_uses_one_query_and_one_vendor_call(
    django_assert_num_queries,
) -> None:
    manufacturer = ManufacturerFactory()
    candidate_ips = [f"2001:db8::{index:x}" for index in range(1, 1025)]
    plugin = Mock()
    plugin.add_discovery_ips.return_value = True
    summary = DiscoverySyncSummary(manufacturer=manufacturer.pk)

    with django_assert_num_queries(1):
        DiscoverySyncService().submit_candidates(
            manufacturer,
            missing_ips=candidate_ips,
            scanned_ips=[],
            plugin=plugin,
            summary=summary,
        )

    plugin.add_discovery_ips.assert_called_once_with(candidate_ips)
    assert summary.missing_ips_submitted == 1024


def test_collect_scanned_candidates_combines_and_deduplicates_sources() -> None:
    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        return_value=(
            {
                "one.example.test": ["192.0.2.1"],
                "two.example.test": ["192.0.2.62"],
            },
            True,
        ),
    ) as resolve:
        page = DiscoverySyncService.collect_scanned_candidates(
            cidrs=["192.0.2.0/30"],
            fqdns=["one.example.test", "two.example.test"],
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=8,
        )

    resolve.assert_called_once_with(["one.example.test", "two.example.test"])
    assert page.candidates == ["192.0.2.1", "192.0.2.2", "192.0.2.62"]
    assert page.sources_complete is True


def test_collect_scanned_candidates_enforces_one_limit_across_all_sources() -> None:
    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        return_value=({"receiver.example.test": ["203.0.113.1"]}, True),
    ) as resolve:
        page = DiscoverySyncService.collect_scanned_candidates(
            cidrs=["192.0.2.0/30", "198.51.100.0/30"],
            fqdns=["receiver.example.test"],
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=2,
        )

    assert page.candidates == ["192.0.2.1", "198.51.100.1"]
    assert page.sources_complete is False
    resolve.assert_called_once_with(["receiver.example.test"])


def test_collect_scanned_candidates_honors_rotating_source_priority() -> None:
    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        return_value=({"receiver.example.test": ["198.51.100.50"]}, True),
    ):
        page = DiscoverySyncService.collect_scanned_candidates(
            cidrs=["192.0.2.0/30"],
            fqdns=["receiver.example.test"],
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=1,
            source_order=["fqdns", "cidrs"],
        )

    assert page.candidates == ["198.51.100.50"]
    assert page.sources_complete is False


def test_collect_scanned_candidates_caps_fqdn_results_and_handles_zero_limit() -> None:
    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        return_value=(
            {"receiver.example.test": ["192.0.2.60", "192.0.2.61", "192.0.2.62"]},
            True,
        ),
    ):
        page = DiscoverySyncService.collect_scanned_candidates(
            cidrs=[],
            fqdns=["receiver.example.test"],
            scan_cidrs=False,
            scan_fqdns=True,
            max_hosts=2,
        )

    assert page.candidates == ["192.0.2.60", "192.0.2.61"]
    assert page.sources_complete is False
    zero = DiscoverySyncService.collect_scanned_candidates(
        cidrs=["192.0.2.0/24"],
        fqdns=["receiver.example.test"],
        scan_cidrs=True,
        scan_fqdns=True,
        max_hosts=0,
    )
    assert zero.candidates == []
    assert zero.sources_complete is False


@pytest.mark.parametrize(
    ("scan_cidrs", "scan_fqdns"),
    [(False, False), (True, True)],
)
def test_collect_scanned_candidates_skips_disabled_or_empty_sources(
    scan_cidrs: bool,
    scan_fqdns: bool,
) -> None:
    with (
        patch("micboard.services.sync.discovery_utils.resolve_fqdns") as resolve,
    ):
        page = DiscoverySyncService.collect_scanned_candidates(
            cidrs=[],
            fqdns=[],
            scan_cidrs=scan_cidrs,
            scan_fqdns=scan_fqdns,
            max_hosts=8,
        )

    assert page.candidates == []
    assert page.sources_complete is True
    resolve.assert_not_called()
