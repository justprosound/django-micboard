"""Behavioral branch coverage for reusable service-layer helpers."""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from micboard.discovery import network_utils
from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.services.shared import access_policy, rate_limiting, tenant_filters
from micboard.services.shared.pagination import PaginatedResult, filter_by_search, paginate_queryset
from micboard.services.shared.sync_utils import SyncResult, get_model_changes, merge_sync_results


def test_expand_cidrs_is_lazy_bounded_and_skips_invalid_ranges() -> None:
    assert list(network_utils.expand_cidrs(["invalid", "192.0.2.0/30"], max_hosts=8)) == [
        "192.0.2.1",
        "192.0.2.2",
    ]
    assert list(network_utils.expand_cidrs(["10.0.0.0/8"], max_hosts=2)) == [
        "10.0.0.1",
        "10.0.0.2",
    ]
    assert list(network_utils.expand_cidrs(["192.0.2.0/24"], max_hosts=0)) == []
    assert list(
        network_utils.expand_cidrs(
            ["192.0.2.0/30", "198.51.100.0/30"],
            max_hosts=3,
        )
    ) == ["192.0.2.1", "192.0.2.2", "198.51.100.1"]
    assert (
        len(list(network_utils.expand_cidrs(["10.0.0.0/8"], max_hosts=10**9)))
        == MAX_DISCOVERY_CANDIDATES
    )


def test_resolve_fqdns_returns_sorted_unique_addresses_and_completeness(monkeypatch) -> None:
    responses = {
        "ok.test": [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.2", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.2", 0)),
        ]
    }

    def resolve(host: str, _port: None):
        if host == "down.test":
            raise socket.gaierror("unavailable")
        return responses[host]

    monkeypatch.setattr(network_utils.socket, "getaddrinfo", resolve)

    result, complete = network_utils.resolve_fqdns(["ok.test", "down.test"])

    assert result == {
        "ok.test": ["192.0.2.1", "192.0.2.2"],
        "down.test": [],
    }
    assert complete is False
    assert network_utils.resolve_fqdns([]) == ({}, True)


@pytest.mark.parametrize(
    ("is_superuser", "cross_org", "expected"),
    [(True, True, True), (True, False, False), (False, True, False)],
)
def test_unrestricted_tenant_access_requires_both_conditions(
    monkeypatch, is_superuser: bool, cross_org: bool, expected: bool
) -> None:
    monkeypatch.setattr(
        access_policy.settings,
        "MICBOARD_ALLOW_CROSS_ORG_VIEW",
        cross_org,
        raising=False,
    )
    assert (
        access_policy.has_unrestricted_tenant_access(SimpleNamespace(is_superuser=is_superuser))
        is expected
    )


class _FakeQuerySet:
    def __init__(self, values):
        self.values = values
        self.filtered = None

    def count(self):
        return len(self.values)

    def __getitem__(self, item):
        return self.values[item]

    def filter(self, query):
        self.filtered = query
        return self


def test_pagination_and_search_helpers_cover_boundaries() -> None:
    queryset = _FakeQuerySet([1, 2, 3, 4, 5])
    page = paginate_queryset(queryset=queryset, page=2, page_size=2)
    assert page == PaginatedResult(items=[3, 4], total_count=5, page=2, page_size=2)
    assert page.total_pages == 3
    assert page.has_next is True
    assert page.has_previous is True
    first = PaginatedResult(items=[], total_count=0, page=1, page_size=20)
    assert first.total_pages == 0
    assert first.has_next is False
    assert first.has_previous is False
    assert filter_by_search(queryset=queryset, search_fields=["name"], query="") is queryset
    assert (
        filter_by_search(
            queryset=queryset,
            search_fields=["name", "code"],
            query="vendor",
        )
        is queryset
    )
    assert queryset.filtered is not None


def test_rate_limit_success_limit_and_cache_failures(monkeypatch) -> None:
    monkeypatch.setattr(rate_limiting.time, "time", Mock(return_value=100.0))
    cache_get = Mock(return_value=[90.0, 99.0])
    cache_set = Mock()
    monkeypatch.setattr(rate_limiting.cache, "get", cache_get)
    monkeypatch.setattr(rate_limiting.cache, "set", cache_set)

    allowed, retry_after, times = rate_limiting.check_rate_limit("client", 3, 10)
    assert allowed is True
    assert retry_after is None
    assert times == [99.0, 100.0]
    cache_set.assert_called_once_with("client_window", times, timeout=11)

    cache_get.return_value = [99.0, 99.5, 99.75]
    allowed, retry_after, times = rate_limiting.check_rate_limit("client", 3, 10)
    assert allowed is False
    assert retry_after == 10
    assert len(times) == 3

    cache_get.side_effect = RuntimeError("cache down")
    cache_set.side_effect = RuntimeError("cache down")
    assert rate_limiting.check_rate_limit("client", 1, 10)[0] is True


def test_rate_limit_request_identity_helpers() -> None:
    forwarded = SimpleNamespace(
        headers={"x-forwarded-for": "198.51.100.3, 198.51.100.4"},
        META={"REMOTE_ADDR": "192.0.2.1"},
    )
    direct = SimpleNamespace(headers={}, META={"REMOTE_ADDR": "192.0.2.1"})
    unknown = SimpleNamespace(headers={}, META={})
    assert rate_limiting.get_client_ip(forwarded) == "198.51.100.3"
    assert rate_limiting.get_client_ip(direct) == "192.0.2.1"
    assert rate_limiting.get_client_ip(unknown) == "unknown"
    authenticated = SimpleNamespace(
        headers={},
        META={},
        user=SimpleNamespace(is_authenticated=True, id=7),
    )
    assert rate_limiting.get_user_cache_key(authenticated, "view") == "rate_limit_user_7"
    assert rate_limiting.get_user_cache_key(direct, "view") == ("rate_limit_anon_view_192.0.2.1")


def test_sync_helpers_report_changes_errors_and_aggregate() -> None:
    first = SyncResult(True, 1, 2, 3, [])
    second = SyncResult(False, 4, 5, 6, ["failed"])
    first.add_error(message="warning")
    assert first.total_changes == 6
    assert get_model_changes(
        instance=SimpleNamespace(name="new", unchanged=1),
        old_values={"name": "old", "unchanged": 1},
    ) == {"name": "new"}
    merged = merge_sync_results(first, second)
    assert merged == SyncResult(False, 5, 7, 9, ["warning", "failed"])


@pytest.mark.parametrize(
    ("settings_value", "kwargs", "expected_filters"),
    [
        (
            SimpleNamespace(msp_enabled=True, multi_site_mode=False),
            {"organization_id": 3, "campus_id": 4},
            [
                {"location__building__organization_id": 3},
                {"location__building__campus_id": 4},
            ],
        ),
        (
            SimpleNamespace(msp_enabled=False, multi_site_mode=True),
            {"site_id": 5},
            [{"location__building__site_id": 5}],
        ),
        (
            SimpleNamespace(msp_enabled=False, multi_site_mode=False),
            {},
            [],
        ),
    ],
)
def test_tenant_filters_follow_configured_scope(
    monkeypatch, settings_value, kwargs, expected_filters
) -> None:
    queryset = MagicMock()
    current = queryset
    calls = []

    def filtered(**filters):
        calls.append(filters)
        return current

    queryset.filter.side_effect = filtered
    monkeypatch.setattr(tenant_filters, "settings", settings_value)
    assert tenant_filters.apply_tenant_filters(queryset, **kwargs) is queryset
    assert calls == expected_filters


def test_tenant_filters_skip_missing_optional_identifiers(monkeypatch) -> None:
    queryset = MagicMock()
    monkeypatch.setattr(
        tenant_filters,
        "settings",
        SimpleNamespace(msp_enabled=True, multi_site_mode=False),
    )
    assert tenant_filters.apply_tenant_filters(queryset) is queryset
    queryset.filter.assert_not_called()

    monkeypatch.setattr(
        tenant_filters,
        "settings",
        SimpleNamespace(msp_enabled=False, multi_site_mode=True),
    )
    assert tenant_filters.apply_tenant_filters(queryset) is queryset
    queryset.filter.assert_not_called()
