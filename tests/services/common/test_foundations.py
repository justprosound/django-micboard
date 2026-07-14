"""Behavioral coverage for shared service foundations."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.services.common.base import plugin as plugin_module
from micboard.services.common.base import rate_limiter as limiter_module
from micboard.services.common.base import resilience as resilience_module
from micboard.services.common.base.client import BaseAPIClient
from micboard.services.common.base.plugin import BasePlugin, ManufacturerPlugin
from micboard.services.common.base.utils import (
    validate_hostname,
    validate_ipv4_address,
    validate_ipv4_list,
)


class PreferredPlugin(ManufacturerPlugin):
    """Concrete plugin used to verify dynamic discovery."""

    name = "Preferred"
    code = "preferred"

    def get_devices(self):
        return []

    def get_device_channels(self, device_id):
        return []

    def get_client(self):
        return Mock()

    def transform_device_data(self, api_data):
        return api_data

    def get_device(self, device_id):
        return None

    def is_healthy(self):
        return True

    def check_health(self):
        return {"status": "healthy"}

    def add_discovery_ips(self, ips):
        return True

    def get_discovery_ips(self):
        return []

    def remove_discovery_ips(self, ips):
        return True


def test_resilient_session_configures_pool_and_retry_transport(monkeypatch) -> None:
    client_factory = Mock(return_value=Mock())
    limits_factory = Mock(return_value="limits")
    transport_factory = Mock(return_value="transport")
    monkeypatch.setattr(resilience_module.httpx, "Client", client_factory)
    monkeypatch.setattr(resilience_module.httpx, "Limits", limits_factory)
    monkeypatch.setattr(resilience_module.httpx, "HTTPTransport", transport_factory)

    result = resilience_module.create_resilient_session(
        max_retries=4,
        pool_connections=7,
        pool_maxsize=11,
        follow_redirects=False,
    )

    assert result is client_factory.return_value
    limits_factory.assert_called_once_with(max_connections=11, max_keepalive_connections=7)
    transport_factory.assert_called_once_with(retries=4)
    client_factory.assert_called_once_with(
        follow_redirects=False,
        limits="limits",
        transport="transport",
    )


def test_rate_limiter_sleeps_only_inside_window(monkeypatch) -> None:
    clock = iter([10.0, 10.0, 10.25, 12.0])
    monkeypatch.setattr(limiter_module.time, "time", lambda: next(clock))
    sleep = Mock()
    monkeypatch.setattr(limiter_module.time, "sleep", sleep)
    monkeypatch.setattr(limiter_module.cache, "get", Mock(side_effect=[9.75, 0]))
    cache_set = Mock()
    monkeypatch.setattr(limiter_module.cache, "set", cache_set)

    class Service:
        @limiter_module.rate_limit(calls_per_second=2)
        def operation(self, value: int) -> int:
            return value * 2

    service = Service()
    assert service.operation(3) == 6
    assert service.operation(4) == 8
    sleep.assert_called_once_with(0.25)
    assert cache_set.call_count == 2


def test_address_and_hostname_validation_covers_invalid_shapes(caplog) -> None:
    assert validate_ipv4_list(["192.0.2.1", "2001:db8::1", "bad"], "vendor") == ["192.0.2.1"]
    assert validate_ipv4_list(["2001:db8::1", "bad"]) == []
    assert validate_ipv4_address("198.51.100.2")
    assert not validate_ipv4_address("2001:db8::1")
    assert not validate_ipv4_address("bad")
    assert validate_hostname("receiver-1.example.test")
    assert validate_hostname("192.0.2.5")
    for invalid in ("", "x" * 254, "bad..host", "-bad", "bad-", "bad_host"):
        assert not validate_hostname(invalid)
    assert not validate_hostname(f"{'x' * 64}.test")
    assert "vendor: Rejected 2 invalid or non-IPv4 addresses" in caplog.text
    assert "Rejected 2 invalid or non-IPv4 addresses" in caplog.text
    assert "2001:db8::1" not in caplog.text


def test_plugin_loader_prefers_named_then_falls_back(monkeypatch) -> None:
    module = ModuleType("plugin")
    module.MyVendorPlugin = PreferredPlugin
    monkeypatch.setattr(plugin_module.importlib, "import_module", Mock(return_value=module))
    assert plugin_module.get_manufacturer_plugin("my_vendor") is PreferredPlugin

    module.MyVendorPlugin = "not a plugin"
    module.Fallback = PreferredPlugin
    assert plugin_module.get_manufacturer_plugin("my_vendor") is PreferredPlugin

    instance = object.__new__(PreferredPlugin)
    BasePlugin.__init__(instance, manufacturer="vendor-row")
    assert instance.manufacturer == "vendor-row"


def test_plugin_loader_reports_missing_module_and_subclass(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_module.importlib,
        "import_module",
        Mock(side_effect=ModuleNotFoundError("missing")),
    )
    with pytest.raises(ModuleNotFoundError, match="No integration module"):
        plugin_module.get_manufacturer_plugin("missing")

    monkeypatch.setattr(
        plugin_module.importlib, "import_module", Mock(return_value=ModuleType("empty"))
    )
    with pytest.raises(ImportError, match="No ManufacturerPlugin subclass"):
        plugin_module.get_manufacturer_plugin("empty")


@pytest.mark.parametrize(
    ("owner", "method", "args"),
    [
        (BaseAPIClient, "is_healthy", ()),
        (BaseAPIClient, "check_health", ()),
        (BaseAPIClient, "_make_request", ("GET", "/")),
        (BasePlugin, "name", ()),
        (BasePlugin, "code", ()),
        (BasePlugin, "get_devices", ()),
        (ManufacturerPlugin, "get_device_channels", ("id",)),
        (ManufacturerPlugin, "get_client", ()),
        (ManufacturerPlugin, "transform_device_data", ({},)),
        (ManufacturerPlugin, "get_device", ("id",)),
        (ManufacturerPlugin, "is_healthy", ()),
        (ManufacturerPlugin, "check_health", ()),
        (ManufacturerPlugin, "add_discovery_ips", ([],)),
        (ManufacturerPlugin, "get_discovery_ips", ()),
        (ManufacturerPlugin, "remove_discovery_ips", ([],)),
    ],
)
def test_abstract_contract_methods_fail_explicitly(
    owner, method: str, args: tuple[object, ...]
) -> None:
    instance = SimpleNamespace()
    descriptor = owner.__dict__[method]
    callable_method = descriptor.fget if isinstance(descriptor, property) else descriptor
    with pytest.raises(NotImplementedError):
        callable_method(instance, *args)
