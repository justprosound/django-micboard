"""Behavioral coverage for supported discovery and diagnostic commands."""

from __future__ import annotations

from argparse import ArgumentParser
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.management.commands import diagnostic_api_health_check as health_command
from micboard.management.commands import discovery_add_devices as add_command
from micboard.management.commands import sync_discovery as sync_command
from micboard.services.sync.discovery_dtos import DiscoveryCandidateSubmission


@pytest.mark.parametrize(
    "command_type",
    [
        health_command.Command,
        add_command.Command,
        sync_command.Command,
    ],
)
def test_discovery_command_argument_contracts(command_type) -> None:
    parser = ArgumentParser(add_help=False)
    command_type().add_arguments(parser)
    assert parser.format_help()


def test_health_checker_requires_key_and_handles_client_initialization(monkeypatch) -> None:
    monkeypatch.setattr(
        health_command.settings, "get", Mock(side_effect=["https://api.test", None])
    )
    with pytest.raises(ValueError, match="SHURE_API_SHARED_KEY"):
        health_command.HealthChecker()

    monkeypatch.setattr(
        health_command.settings,
        "get",
        Mock(side_effect=["https://api.test", "secret"]),
    )
    monkeypatch.setattr(
        health_command,
        "ShureSystemAPIClient",
        Mock(side_effect=RuntimeError("TLS-secret-SENTINEL")),
    )
    checker = health_command.HealthChecker()
    assert checker.client is None
    assert checker.error == "Client initialization failed (RuntimeError); details redacted."
    assert "SENTINEL" not in checker.error


def _checker(client=None):
    checker = health_command.HealthChecker.__new__(health_command.HealthChecker)
    checker.base_url = "https://api.test"
    checker.client = client
    checker.error = "not initialized"
    return checker


def test_health_connectivity_paths() -> None:
    assert _checker().check_connectivity() == {"status": "failed", "error": "not initialized"}
    client = Mock()
    client.check_health.side_effect = [
        {"status": "healthy", "status_code": 200},
        {"status": "unhealthy", "status_code": 503, "error": "offline"},
        RuntimeError("timeout-secret-SENTINEL"),
    ]
    checker = _checker(client)
    assert checker.check_connectivity()["status"] == "healthy"
    assert checker.check_connectivity()["status"] == "unhealthy"
    assert checker.check_connectivity() == {
        "status": "failed",
        "error": "Connectivity check failed (RuntimeError); details redacted.",
    }


def test_health_device_and_ip_paths() -> None:
    assert _checker().check_devices() == {}
    assert _checker().check_discovery_ips() == {}
    client = Mock()
    client.devices.get_devices.side_effect = [
        [],
        [{"state": "ONLINE"}, {"state": "ONLINE"}, {}],
        RuntimeError("devices failed"),
    ]
    client.discovery.get_discovery_ips.side_effect = [
        [],
        ["192.0.2.1", "192.0.2.2", "198.51.100.1"],
        RuntimeError("IPs failed"),
    ]
    checker = _checker(client)
    assert checker.check_devices()["device_count"] == 0
    assert checker.check_devices()["device_count"] == 3
    assert checker.check_devices() == {}
    assert checker.check_discovery_ips()["ip_count"] == 0
    assert checker.check_discovery_ips()["ip_count"] == 3
    assert checker.check_discovery_ips() == {}


def test_health_endpoint_and_client_configuration_paths() -> None:
    assert _checker().check_api_endpoints() == {}
    assert _checker().check_client_config() == {}
    client = Mock()
    client.base_url = "https://api.test"
    client.timeout = 5
    client.max_retries = 2
    client.retry_backoff = 1
    client.is_healthy.side_effect = [True, False]
    client.client.get.side_effect = [
        SimpleNamespace(status_code=200),
        RuntimeError("endpoint-secret-SENTINEL"),
    ]
    checker = _checker(client)
    endpoints = checker.check_api_endpoints()
    assert endpoints["/api/v1/devices"] == 200
    endpoint_error = str(endpoints["/api/v1/config/discovery/ips"])
    assert endpoint_error.startswith("ERROR (RuntimeError): details redacted.")
    assert "SENTINEL" not in endpoint_error
    config = checker.check_client_config()
    assert config["base_url"] == "https://api.test"
    assert config["is_healthy"] is False


def test_health_summary_recommendations_and_command_error(monkeypatch) -> None:
    checker = _checker(Mock())
    checker.check_connectivity = Mock(return_value={"status": "failed"})
    checker.check_devices = Mock(return_value={"device_count": 0})
    checker.check_discovery_ips = Mock(return_value={"ip_count": 2})
    checker.check_api_endpoints = Mock()
    checker.check_client_config = Mock()
    checker.print_summary(full=True)
    checker.check_discovery_ips.return_value = {"ip_count": 0}
    checker.print_summary()
    checker.check_connectivity.return_value = {"status": "healthy"}
    checker.check_devices.return_value = {"device_count": 1}
    checker.check_discovery_ips.return_value = {"ip_count": 1}
    checker.run(full=True)

    run = Mock()
    monkeypatch.setattr(
        health_command, "HealthChecker", Mock(return_value=SimpleNamespace(run=run))
    )
    health_command.Command().handle(full=True)
    run.assert_called_once_with(full=True)
    monkeypatch.setattr(
        health_command,
        "HealthChecker",
        Mock(side_effect=RuntimeError("fatal-secret-SENTINEL")),
    )
    errors = StringIO()
    health_command.Command(stderr=errors).handle(full=False)
    assert "Fatal error (RuntimeError); details redacted." in errors.getvalue()
    assert "SENTINEL" not in errors.getvalue()


def test_discovery_add_devices_validation_and_results(monkeypatch) -> None:
    errors = StringIO()
    output = StringIO()
    command = add_command.Command(stdout=output, stderr=errors)
    monkeypatch.setattr(
        add_command.Manufacturer.objects,
        "get",
        Mock(side_effect=add_command.Manufacturer.DoesNotExist),
    )
    command.handle(manufacturer="missing", ips="192.0.2.1")
    assert "not found" in errors.getvalue()

    manufacturer = SimpleNamespace(name="Shure")
    add_command.Manufacturer.objects.get.side_effect = None
    add_command.Manufacturer.objects.get.return_value = manufacturer
    command.handle(manufacturer="shure", ips=" , ")
    assert "No valid IP" in errors.getvalue()

    submit = Mock(
        return_value=DiscoveryCandidateSubmission(
            submitted_ips=["192.0.2.1"],
            failed_ips=["2001:db8::1"],
            rejected_count=1,
        )
    )
    monkeypatch.setattr(
        add_command,
        "DiscoveryService",
        Mock(return_value=SimpleNamespace(add_discovery_candidates=submit)),
    )
    command.handle(
        manufacturer="shure",
        ips="192.0.2.1,2001:0db8::1,invalid,192.0.2.1",
    )

    submit.assert_called_once_with(manufacturer, ["192.0.2.1", "2001:db8::1"])
    assert "Submitted 1 discovery candidates; rejected 3" in output.getvalue()


def test_discovery_add_devices_rejects_oversized_input_before_service_call(monkeypatch) -> None:
    manufacturer = SimpleNamespace(name="Shure")
    monkeypatch.setattr(add_command.Manufacturer.objects, "get", Mock(return_value=manufacturer))
    discovery_service = Mock()
    monkeypatch.setattr(add_command, "DiscoveryService", Mock(return_value=discovery_service))
    errors = StringIO()

    add_command.Command(stderr=errors).handle(
        manufacturer="shure",
        ips=",".join("192.0.2.1" for _index in range(MAX_DISCOVERY_CANDIDATES + 1)),
    )

    assert "exceeds hard limit" in errors.getvalue()
    discovery_service.add_discovery_candidates.assert_not_called()
