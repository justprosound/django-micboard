"""Focused tests for device probing and API health checks."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call

import httpx
import pytest

from micboard.services.common.base import resilience
from micboard.services.sync import device_probe_service as probe_module
from micboard.services.sync.device_probe_service import DeviceAPIHealthChecker, DeviceProbeService


def _response(status_code: int) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return response


def _request_error() -> httpx.RequestError:
    request = httpx.Request("GET", "http://192.0.2.10/api/health")
    return httpx.RequestError("offline", request=request)


@pytest.fixture
def probe_service(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[DeviceProbeService, MagicMock, MagicMock]:
    session = MagicMock(spec=httpx.Client)
    session_factory = MagicMock(return_value=session)
    monkeypatch.setattr(resilience, "create_resilient_session", session_factory)
    service = DeviceProbeService(timeout=7)
    return service, session, session_factory


@pytest.fixture
def health_checker(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[DeviceAPIHealthChecker, MagicMock, MagicMock]:
    session = MagicMock(spec=httpx.Client)
    client_factory = MagicMock(return_value=session)
    monkeypatch.setattr(probe_module.httpx, "Client", client_factory)
    checker = DeviceAPIHealthChecker("https://api.example.test/")
    return checker, session, client_factory


def test_probe_service_configures_resilient_session_and_circuit(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
) -> None:
    service, session, session_factory = probe_service

    assert service.timeout == 7
    assert service.session is session
    assert service.discovered_devices == []
    assert service._circuit.state == "closed"
    session_factory.assert_called_once_with(max_retries=3)


def test_create_session_preserves_mandatory_certificate_verification(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
) -> None:
    service, session, session_factory = probe_service
    session_factory.reset_mock()

    assert service._create_session() is session
    session_factory.assert_called_once_with(max_retries=3)


def test_probe_device_fast_fails_when_circuit_is_open(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
) -> None:
    service, session, _session_factory = probe_service
    for _ in range(3):
        service._circuit.record_failure()

    assert service.probe_device("192.0.2.10") is None
    session.get.assert_not_called()


def test_probe_device_returns_accessible_endpoint_and_resets_circuit(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
) -> None:
    service, session, _session_factory = probe_service
    service._circuit.record_failure()
    session.get.return_value = _response(200)

    assert service.probe_device("192.0.2.10") == {
        "ip": "192.0.2.10",
        "endpoint": "http://192.0.2.10/api/v1/devices",
        "accessible": True,
        "needs_auth": False,
    }
    assert service._circuit.state == "closed"
    session.get.assert_called_once_with(
        "http://192.0.2.10/api/v1/devices",
        timeout=7,
        follow_redirects=False,
    )


def test_probe_device_accepts_auth_challenge_after_nonmatching_response(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
) -> None:
    service, session, _session_factory = probe_service
    session.get.side_effect = [_response(404), _response(401)]

    assert service.probe_device("192.0.2.10") == {
        "ip": "192.0.2.10",
        "endpoint": "https://192.0.2.10/api/v1/devices",
        "accessible": False,
        "needs_auth": True,
    }
    assert session.get.call_count == 2


def test_probe_device_records_request_failures_and_opens_circuit(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, session, _session_factory = probe_service
    session.get.side_effect = _request_error()

    with caplog.at_level(logging.DEBUG, logger=probe_module.__name__):
        assert service.probe_device("192.0.2.10") is None

    assert session.get.call_count == 4
    assert service._circuit.state == "open"
    assert "192.0.2.10" not in caplog.text


def test_probe_device_returns_none_when_endpoints_are_not_device_apis(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
) -> None:
    service, session, _session_factory = probe_service
    session.get.return_value = _response(404)

    assert service.probe_device("192.0.2.10") is None
    assert session.get.call_count == 4
    assert service._circuit.state == "closed"


def test_probe_ips_strips_addresses_and_replaces_previous_results(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _session, _session_factory = probe_service
    service.discovered_devices = [{"ip": "stale"}]
    probe = MagicMock(side_effect=[{"ip": "192.0.2.10"}, None])
    monkeypatch.setattr(service, "probe_device", probe)

    result = service.probe_ips([" 192.0.2.10 ", "192.0.2.11"])

    assert result == [{"ip": "192.0.2.10"}]
    assert service.get_discovered_devices() is result
    assert probe.call_args_list == [call("192.0.2.10"), call("192.0.2.11")]


def test_probe_from_file_ignores_comments_and_blank_lines(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, _session, _session_factory = probe_service
    ip_file = tmp_path / "devices.txt"
    ip_file.write_text("# lab receivers\n\n192.0.2.10\n 192.0.2.11 \n", encoding="utf-8")
    probe_ips = MagicMock(return_value=[{"ip": "192.0.2.10"}])
    monkeypatch.setattr(service, "probe_ips", probe_ips)

    assert service.probe_from_file(str(ip_file)) == [{"ip": "192.0.2.10"}]
    probe_ips.assert_called_once_with(["192.0.2.10", "192.0.2.11"])


def test_probe_from_file_returns_empty_for_missing_path(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    service, _session, _session_factory = probe_service

    assert service.probe_from_file(str(tmp_path / "missing.txt")) == []


def test_probe_from_env_parses_nonempty_addresses(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _session, _session_factory = probe_service
    monkeypatch.setenv("LAB_DEVICE_IPS", "192.0.2.10, , 192.0.2.11 ")
    probe_ips = MagicMock(return_value=[{"ip": "192.0.2.11"}])
    monkeypatch.setattr(service, "probe_ips", probe_ips)

    assert service.probe_from_env(env_var="LAB_DEVICE_IPS") == [{"ip": "192.0.2.11"}]
    probe_ips.assert_called_once_with(["192.0.2.10", "192.0.2.11"])


def test_probe_from_env_returns_empty_when_variable_is_missing(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _session, _session_factory = probe_service
    monkeypatch.delenv("LAB_DEVICE_IPS", raising=False)

    assert service.probe_from_env(env_var="LAB_DEVICE_IPS") == []


def test_save_discovery_manifest_includes_metadata(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    service, _session, _session_factory = probe_service
    service.discovered_devices = [{"ip": "192.0.2.10", "accessible": True}]
    manifest_path = tmp_path / "manifest.json"

    service.save_discovery_manifest(str(manifest_path))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["devices"] == service.discovered_devices
    assert manifest["total_count"] == 1
    assert datetime.fromisoformat(manifest["timestamp"])


def test_save_discovery_manifest_can_omit_metadata(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    service, _session, _session_factory = probe_service
    service.discovered_devices = [{"ip": "192.0.2.10"}]
    manifest_path = tmp_path / "manifest.json"

    service.save_discovery_manifest(str(manifest_path), include_metadata=False)

    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {
        "devices": [{"ip": "192.0.2.10"}]
    }


def test_clear_discovered_devices_replaces_collection(
    probe_service: tuple[DeviceProbeService, MagicMock, MagicMock],
) -> None:
    service, _session, _session_factory = probe_service
    original = [{"ip": "192.0.2.10"}]
    service.discovered_devices = original

    service.clear_discovered_devices()

    assert service.get_discovered_devices() == []
    assert service.get_discovered_devices() is not original


def test_health_checker_normalizes_url_and_creates_client(
    health_checker: tuple[DeviceAPIHealthChecker, MagicMock, MagicMock],
) -> None:
    checker, session, client_factory = health_checker

    assert checker.api_base_url == "https://api.example.test"
    assert checker.session is session
    client_factory.assert_called_once_with()


@pytest.mark.parametrize(("status_code", "expected"), [(200, True), (503, False)])
def test_check_health_interprets_response_status(
    health_checker: tuple[DeviceAPIHealthChecker, MagicMock, MagicMock],
    status_code: int,
    expected: bool,
) -> None:
    checker, session, _client_factory = health_checker
    session.get.return_value = _response(status_code)

    assert checker.check_health(timeout=9) is expected
    session.get.assert_called_once_with("https://api.example.test/api/health", timeout=9)


def test_check_health_handles_network_error(
    health_checker: tuple[DeviceAPIHealthChecker, MagicMock, MagicMock],
) -> None:
    checker, session, _client_factory = health_checker
    session.get.side_effect = _request_error()

    assert checker.check_health() is False


def test_get_api_status_reports_reachable_response(
    health_checker: tuple[DeviceAPIHealthChecker, MagicMock, MagicMock],
) -> None:
    checker, session, _client_factory = health_checker
    session.get.return_value = _response(204)

    assert checker.get_api_status(timeout=3) == {
        "healthy": False,
        "status_code": 204,
        "api_url": "https://api.example.test",
        "reachable": True,
    }
    session.get.assert_called_once_with("https://api.example.test/api/health", timeout=3)


def test_get_api_status_reports_unreachable_api(
    health_checker: tuple[DeviceAPIHealthChecker, MagicMock, MagicMock],
) -> None:
    checker, session, _client_factory = health_checker
    session.get.side_effect = _request_error()

    assert checker.get_api_status() == {
        "healthy": False,
        "status_code": None,
        "api_url": "https://api.example.test",
        "reachable": False,
        "error": "offline",
    }


def test_probe_device_ip_delegates_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock(spec=DeviceProbeService)
    service.probe_device.return_value = {"ip": "192.0.2.10"}
    service_factory = MagicMock(return_value=service)
    monkeypatch.setattr(probe_module, "DeviceProbeService", service_factory)

    assert probe_module.probe_device_ip("192.0.2.10", timeout=11) == {"ip": "192.0.2.10"}
    service_factory.assert_called_once_with(timeout=11)
    service.probe_device.assert_called_once_with("192.0.2.10")
