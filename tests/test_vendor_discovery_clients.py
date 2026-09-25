"""Behavioral coverage for vendor discovery clients."""

from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from micboard.integrations.sennheiser.discovery_client import SennheiserDiscoveryClient
from micboard.integrations.sennheiser.exceptions import SennheiserAPIError
from micboard.integrations.shure.discovery_client import ShureDiscoveryClient
from micboard.integrations.shure.exceptions import ShureAPIError
from tests.vendor_test_helpers import disable_rate_limit_waits, vendor_api


@pytest.fixture(autouse=True)
def _disable_rate_limit_waits(monkeypatch) -> None:
    disable_rate_limit_waits(monkeypatch)


@pytest.mark.parametrize(
    ("client_class", "error_class", "prefix"),
    [
        (ShureDiscoveryClient, ShureAPIError, "/api/v1/config/discovery/ips"),
        (SennheiserDiscoveryClient, SennheiserAPIError, "/api/config/discovery/ips"),
    ],
)
def test_discovery_clients_validate_and_parse_lists(client_class, error_class, prefix: str) -> None:
    api = vendor_api(
        None,
        {"ips": ["192.0.2.1"]},
        {"ips": "bad"},
        None,
        error_class("read failed"),
    )
    client = client_class(api)

    assert client.get_discovery_ips() == []
    assert client.get_discovery_ips() == ["192.0.2.1"]
    assert client.get_discovery_ips() == []
    assert client.get_discovery_ips() == []
    assert client.get_discovery_ips() == []
    assert all(request.args[1] == prefix for request in api._make_request.call_args_list)


def test_shure_discovery_add_and_remove_cover_fallbacks() -> None:
    api = vendor_api(
        {"ips": ["192.0.2.1"]},
        None,
        ShureAPIError("existing unavailable"),
        None,
        ShureAPIError("patch unsupported"),
        None,
        ShureAPIError("patch unsupported"),
        ShureAPIError("post failed"),
    )
    client = ShureDiscoveryClient(api)

    assert not client.add_discovery_ips(["invalid"])
    assert client.add_discovery_ips(["192.0.2.1", "192.0.2.2"])
    assert api._make_request.call_args_list[1] == call(
        "PUT",
        "/api/v1/config/discovery/ips",
        json={"ips": ["192.0.2.1", "192.0.2.2"]},
    )
    assert client.add_discovery_ips(["192.0.2.3"])
    assert not client.remove_discovery_ips(["invalid"])
    assert client.remove_discovery_ips(["192.0.2.1"])
    assert not client.remove_discovery_ips(["192.0.2.2"])

    failing = ShureDiscoveryClient(
        vendor_api(ShureAPIError("get failed"), ShureAPIError("put failed"))
    )
    assert not failing.add_discovery_ips(["192.0.2.4"])

    unexpected_existing = ShureDiscoveryClient(vendor_api("unexpected", None))
    assert unexpected_existing.add_discovery_ips(["192.0.2.5"])


def test_shure_discovery_rejects_an_oversized_merged_remote_list(monkeypatch) -> None:
    """Existing and requested addresses cannot bypass the shared discovery bound."""
    monkeypatch.setattr("micboard.integrations.shure.discovery_client.MAX_DISCOVERY_CANDIDATES", 2)
    api = vendor_api({"ips": ["192.0.2.1", "192.0.2.2"]})

    assert not ShureDiscoveryClient(api).add_discovery_ips(["192.0.2.3"])
    api._make_request.assert_called_once_with("GET", "/api/v1/config/discovery/ips")


def test_sennheiser_discovery_add_remove_success_and_failure() -> None:
    api = vendor_api(
        None,
        None,
        SennheiserAPIError("add failed"),
        SennheiserAPIError("remove failed"),
    )
    client = SennheiserDiscoveryClient(api)

    assert not client.add_discovery_ips(["invalid"])
    assert client.add_discovery_ips(["192.0.2.1"])
    assert not client.remove_discovery_ips(["invalid"])
    assert client.remove_discovery_ips(["192.0.2.1"])
    assert not client.add_discovery_ips(["192.0.2.2"])
    assert not client.remove_discovery_ips(["192.0.2.2"])


@pytest.mark.parametrize(
    ("client_class", "side_effect"),
    [
        (
            ShureDiscoveryClient,
            [None, ShureAPIError("vendor-secret-SENTINEL")],
        ),
        (
            SennheiserDiscoveryClient,
            [SennheiserAPIError("vendor-secret-SENTINEL")],
        ),
    ],
)
def test_discovery_client_failures_do_not_log_addresses_or_vendor_details(
    client_class,
    side_effect,
    caplog,
) -> None:
    api = Mock()
    api._make_request.side_effect = side_effect

    with caplog.at_level("ERROR"):
        assert not client_class(api).add_discovery_ips(["10.20.30.40"])

    assert "10.20.30.40" not in caplog.text
    assert "SENTINEL" not in caplog.text
    assert "Failed to add 1 discovery IPs" in caplog.text
