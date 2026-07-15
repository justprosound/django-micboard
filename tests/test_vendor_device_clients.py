"""Behavioral coverage for built-in vendor device clients."""

from __future__ import annotations

import pytest

from micboard.integrations.sennheiser.device_client import SennheiserDeviceClient
from micboard.integrations.sennheiser.exceptions import SennheiserAPIError
from micboard.integrations.shure.device_client import ShureDeviceClient
from micboard.integrations.shure.exceptions import ShureAPIError
from tests.vendor_test_helpers import disable_rate_limit_waits, vendor_api


@pytest.fixture(autouse=True)
def _disable_rate_limit_waits(monkeypatch) -> None:
    disable_rate_limit_waits(monkeypatch)


def test_shure_device_listing_normalizes_graph_and_list_payloads() -> None:
    graph_device = {
        "hardwareIdentity": {"deviceId": "device-1", "serialNumber": "serial-1"},
        "communicationProtocol": {"address": "192.0.2.1"},
        "softwareIdentity": {"model": "ULXD4", "firmwareVersion": "1.2.3"},
    }
    api = vendor_api(
        {"edges": [{"node": graph_device}, {"cursor": "ignored"}]},
        [{"id": "already-flat"}, "not-a-device"],
        {"unexpected": []},
    )
    client = ShureDeviceClient(api)

    assert client.get_devices() == [
        {
            **graph_device,
            "id": "device-1",
            "serialNumber": "serial-1",
            "ipAddress": "192.0.2.1",
            "model": "ULXD4",
            "firmwareVersion": "1.2.3",
        }
    ]
    assert client.get_devices() == [{"id": "already-flat"}]
    assert client.get_devices() == []


def test_shure_device_endpoints_cover_success_empty_and_errors() -> None:
    api = vendor_api(
        ["ULXD", "QLXD"],
        {"unexpected": True},
        ShureAPIError("models unavailable"),
        {"id": "device-1"},
        [{"channel": 1}],
        {"unexpected": True},
    )
    client = ShureDeviceClient(api)

    assert client.get_supported_device_models() == ["ULXD", "QLXD"]
    assert client.get_supported_device_models() == []
    assert client.get_supported_device_models() == []
    assert client.get_device("device-1") == {"id": "device-1"}
    assert client.get_device_channels("device-1") == [{"channel": 1}]
    assert client.get_device_channels("device-1") == []


def test_sennheiser_device_endpoints_cover_success_empty_and_errors() -> None:
    api = vendor_api(
        [{"id": "one"}],
        None,
        ["EW-D"],
        {"unexpected": True},
        SennheiserAPIError("models unavailable"),
        {"id": "one"},
        [{"channel": 1}],
        None,
    )
    client = SennheiserDeviceClient(api)

    assert client.get_devices() == [{"id": "one"}]
    assert client.get_devices() == []
    assert client.get_supported_device_models() == ["EW-D"]
    assert client.get_supported_device_models() == []
    assert client.get_supported_device_models() == []
    assert client.get_device("one") == {"id": "one"}
    assert client.get_device_channels("one") == [{"channel": 1}]
    assert client.get_device_channels("one") == []
