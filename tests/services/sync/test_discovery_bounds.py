"""Resource-bound contracts shared by discovery reconciliation paths."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.sync.discovery_service import DiscoveryService
from micboard.services.sync.discovery_utils import (
    collect_local_candidates,
    prepare_scanning_data,
)
from tests.factories.discovery import (
    DiscoveryCIDRFactory,
    DiscoveryFQDNFactory,
    ManufacturerFactory,
)
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _manufacturer() -> Manufacturer:
    return cast(Manufacturer, ManufacturerFactory())


def test_prepare_scanning_data_lazily_bounds_huge_ipv6_network() -> None:
    """A /64 is sampled lazily instead of materializing its address space."""
    manufacturer = _manufacturer()
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="2001:db8:10::/64")

    cidrs, fqdns, total, complete = prepare_scanning_data(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=False,
        max_hosts=3,
    )

    assert cidrs == {"2001:db8:10::/64": ["2001:db8:10::1", "2001:db8:10::2", "2001:db8:10::3"]}
    assert fqdns == {}
    assert total == 3
    assert complete is False


def test_prepare_scanning_data_shares_one_budget_across_cidrs() -> None:
    manufacturer = _manufacturer()
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="192.0.2.0/30")
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="192.0.2.4/30")

    cidrs, _, total, complete = prepare_scanning_data(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=False,
        max_hosts=3,
    )

    assert cidrs == {
        "192.0.2.0/30": ["192.0.2.1", "192.0.2.2"],
        "192.0.2.4/30": ["192.0.2.5"],
    }
    assert total == 3
    assert complete is False


def test_prepare_scanning_data_shares_budget_with_fqdn_results() -> None:
    manufacturer = _manufacturer()
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="192.0.2.0/30")
    DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn="receiver.example.test")

    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        return_value=(
            {
                "receiver.example.test": [
                    "198.51.100.1",
                    "198.51.100.2",
                    "198.51.100.3",
                ]
            },
            True,
        ),
    ):
        cidrs, fqdns, total, complete = prepare_scanning_data(
            manufacturer,
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=3,
        )

    assert cidrs == {"192.0.2.0/30": ["192.0.2.1", "192.0.2.2"]}
    assert fqdns == {"receiver.example.test": ["198.51.100.1"]}
    assert total == 3
    assert complete is False


def test_prepare_scanning_data_clamps_caller_limit_to_hard_ceiling() -> None:
    manufacturer = _manufacturer()
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="2001:db8:20::/64")

    cidrs, _, total, complete = prepare_scanning_data(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=False,
        max_hosts=10**9,
    )

    assert len(cidrs["2001:db8:20::/64"]) == MAX_DISCOVERY_CANDIDATES
    assert total == MAX_DISCOVERY_CANDIDATES
    assert complete is False


def test_collect_local_candidates_rotates_bounded_pages_and_wraps() -> None:
    manufacturer = _manufacturer()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.10")
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.11")
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.12")

    first, first_complete = collect_local_candidates(manufacturer, limit=2)
    second, second_complete = collect_local_candidates(manufacturer, limit=2)
    third, third_complete = collect_local_candidates(manufacturer, limit=2)
    fourth, fourth_complete = collect_local_candidates(manufacturer, limit=2)

    assert first == ["192.0.2.10", "192.0.2.11"]
    assert second == ["192.0.2.12", "192.0.2.10"]
    assert third == ["192.0.2.11", "192.0.2.12"]
    assert fourth == first
    assert not any((first_complete, second_complete, third_complete, fourth_complete))


def test_collect_local_candidates_fails_open_when_cursor_cache_is_unavailable(caplog) -> None:
    manufacturer = _manufacturer()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.13")
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.14")
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.15")
    secret = "redis-password"

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
        candidates, complete = collect_local_candidates(manufacturer, limit=2)

    assert candidates == ["192.0.2.13", "192.0.2.14"]
    assert complete is False
    assert secret not in caplog.text


def test_zero_budget_does_not_materialize_local_or_network_sources() -> None:
    manufacturer = _manufacturer()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.20")
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="2001:db8:21::/64")
    DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn="receiver.example.test")

    assert collect_local_candidates(manufacturer, limit=0) == ([], False)
    assert prepare_scanning_data(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=True,
        max_hosts=0,
    ) == ({}, {}, 0, False)


def test_invalid_cidr_is_contained_without_spending_shared_budget() -> None:
    manufacturer = _manufacturer()
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="not-a-network")
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="192.0.2.0/30")

    cidrs, _, total, complete = prepare_scanning_data(
        manufacturer,
        scan_cidrs=True,
        scan_fqdns=False,
        max_hosts=2,
    )

    assert cidrs == {
        "not-a-network": [],
        "192.0.2.0/30": ["192.0.2.1", "192.0.2.2"],
    }
    assert total == 2
    assert complete is False


def test_unexpected_resolver_failure_preserves_source_keys() -> None:
    manufacturer = _manufacturer()
    DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn="receiver.example.test")

    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        side_effect=RuntimeError("resolver failed"),
    ):
        _, fqdns, total, complete = prepare_scanning_data(
            manufacturer,
            scan_cidrs=False,
            scan_fqdns=True,
            max_hosts=2,
        )

    assert fqdns == {"receiver.example.test": []}
    assert total == 0
    assert complete is False


def test_shared_scan_budget_attempts_each_selected_source_type() -> None:
    manufacturer = _manufacturer()
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="192.0.2.0/30")
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="192.0.2.4/30")
    DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn="receiver.example.test")

    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        return_value=({"receiver.example.test": ["198.51.100.1"]}, True),
    ) as resolve:
        cidrs, fqdns, total, complete = prepare_scanning_data(
            manufacturer,
            scan_cidrs=True,
            scan_fqdns=True,
            max_hosts=2,
        )

    assert cidrs == {"192.0.2.0/30": ["192.0.2.1"]}
    assert fqdns == {"receiver.example.test": ["198.51.100.1"]}
    assert total == 2
    assert complete is False
    resolve.assert_called_once_with(["receiver.example.test"])


def test_reconciliation_scan_definitions_rotate_to_later_rows_and_wrap() -> None:
    manufacturer = _manufacturer()
    cidrs = [
        DiscoveryCIDRFactory(manufacturer=manufacturer, cidr=f"192.0.2.{index}/32")
        for index in range(3)
    ]
    fqdns = [
        DiscoveryFQDNFactory(manufacturer=manufacturer, fqdn=f"receiver-{index}.example.test")
        for index in range(3)
    ]

    def resolve(names: list[str]) -> tuple[dict[str, list[str]], bool]:
        return {
            name: [f"198.51.100.{int(name.split('-')[1].split('.')[0]) + 1}"] for name in names
        }, True

    with patch(
        "micboard.services.sync.discovery_utils.resolve_fqdns",
        side_effect=resolve,
    ):
        pages = [
            prepare_scanning_data(
                manufacturer,
                scan_cidrs=True,
                scan_fqdns=True,
                max_hosts=2,
            )
            for _index in range(4)
        ]

    assert [
        (list(cidr_map), list(fqdn_map)) for cidr_map, fqdn_map, _total, _complete in pages
    ] == [
        ([cidrs[0].cidr], [fqdns[0].fqdn]),
        ([cidrs[1].cidr], [fqdns[1].fqdn]),
        ([cidrs[2].cidr], [fqdns[2].fqdn]),
        ([cidrs[0].cidr], [fqdns[0].fqdn]),
    ]
    assert all(total == 2 and complete is False for _cidrs, _fqdns, total, complete in pages)


def test_reconciliation_path_reuses_lazy_shared_expansion() -> None:
    manufacturer = _manufacturer()
    WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.35")
    DiscoveryCIDRFactory(manufacturer=manufacturer, cidr="2001:db8:35::/64")
    plugin = MagicMock()
    plugin.get_discovery_ips.return_value = []
    plugin.add_discovery_ips.return_value = True

    with patch(
        "micboard.services.sync.discovery_service.get_manufacturer_plugin_instance",
        return_value=plugin,
    ):
        DiscoveryService().run_manufacturer_discovery(
            manufacturer,
            scan_cidrs=True,
            scan_fqdns=False,
            max_hosts=2,
        )

    plugin.add_discovery_ips.assert_called_once_with(["192.0.2.35", "2001:db8:35::1"])
    plugin.remove_discovery_ips.assert_not_called()
