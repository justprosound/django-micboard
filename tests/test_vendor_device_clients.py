"""Behavioral coverage for built-in vendor device clients."""

from __future__ import annotations

from unittest.mock import Mock

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
        {"battery": 3},
        {"serialNumber": "serial"},
        ShureAPIError("identity unavailable"),
        {"hostname": "receiver"},
        ShureAPIError("network unavailable"),
        {"frequencyBand": "G50"},
        ShureAPIError("status unavailable"),
    )
    client = ShureDeviceClient(api)

    assert client.get_supported_device_models() == ["ULXD", "QLXD"]
    assert client.get_supported_device_models() == []
    assert client.get_supported_device_models() == []
    assert client.get_device("device-1") == {"id": "device-1"}
    assert client.get_device_channels("device-1") == [{"channel": 1}]
    assert client.get_device_channels("device-1") == []
    assert client.get_transmitter_data("device-1", 1) == {"battery": 3}
    assert client.get_device_identity("device-1") == {"serialNumber": "serial"}
    assert client.get_device_identity("device-1") is None
    assert client.get_device_network("device-1") == {"hostname": "receiver"}
    assert client.get_device_network("device-1") is None
    assert client.get_device_status("device-1") == {"frequencyBand": "G50"}
    assert client.get_device_status("device-1") is None


def test_shure_enrichment_merges_available_optional_fields() -> None:
    client = ShureDeviceClient(vendor_api())
    client.get_device_identity = Mock(
        return_value={"serialNumber": "serial", "modelVariant": "quad", "firmwareVersion": "2.0"}
    )
    client.get_device_network = Mock(return_value={"hostname": "rack", "macAddress": "aa:bb"})
    client.get_device_status = Mock(return_value={"frequencyBand": "G50", "location": "stage"})
    original = {"serial_number": "keep"}

    assert client._enrich_device_data("device-1", original) == {
        "serial_number": "keep",
        "model_variant": "quad",
        "firmware_version": "2.0",
        "hostname": "rack",
        "mac_address": "aa:bb",
        "frequency_band": "G50",
        "location": "stage",
    }

    client.get_device_identity.return_value = None
    client.get_device_network.return_value = None
    client.get_device_status.return_value = None
    assert client._enrich_device_data("device-1", {}) == {}

    client.get_device_identity.return_value = {"serialNumber": "serial"}
    client.get_device_network.return_value = ["unexpected"]
    client.get_device_status.return_value = ["unexpected"]
    assert client._enrich_device_data("device-1", {}) == {
        "serial_number": "serial",
        "model_variant": None,
    }


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
        {"battery": 2},
        {"serialNumber": "serial"},
        SennheiserAPIError("identity unavailable"),
        {"hostname": "receiver"},
        SennheiserAPIError("network unavailable"),
        {"location": "stage"},
        SennheiserAPIError("status unavailable"),
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
    assert client.get_transmitter_data("one", 1) == {"battery": 2}
    assert client.get_device_identity("one") == {"serialNumber": "serial"}
    assert client.get_device_identity("one") is None
    assert client.get_device_network("one") == {"hostname": "receiver"}
    assert client.get_device_network("one") is None
    assert client.get_device_status("one") == {"location": "stage"}
    assert client.get_device_status("one") is None


def test_sennheiser_enrichment_and_polling_tolerate_partial_devices() -> None:
    client = SennheiserDeviceClient(vendor_api())
    client.get_device_identity = Mock(
        return_value={"serialNumber": "serial", "modelVariant": "dual", "firmwareVersion": "3.0"}
    )
    client.get_device_network = Mock(return_value={"hostname": "rack", "macAddress": "aa:cc"})
    client.get_device_status = Mock(return_value={"frequencyBand": "R1", "location": "studio"})
    assert client._enrich_device_data("one", {})["firmware_version"] == "3.0"
    client.get_device_identity.return_value = {"serialNumber": "serial"}
    client.get_device_network.return_value = ["unexpected"]
    client.get_device_status.return_value = ["unexpected"]
    assert client._enrich_device_data("one", {}) == {
        "serial_number": "serial",
        "model_variant": None,
    }
    client.get_device_identity.return_value = ["unexpected"]
    client.get_device_network.return_value = None
    client.get_device_status.return_value = None
    assert client._enrich_device_data("one", {}) == {}

    client.get_devices = Mock(
        return_value=[
            {},
            {"id": "empty"},
            {"id": "bad"},
            {"id": "untransformable"},
            {"id": "good"},
        ]
    )
    client.get_device = Mock(
        side_effect=[
            None,
            SennheiserAPIError("offline"),
            {"id": "untransformable"},
            {"id": "good"},
        ]
    )
    client._enrich_device_data = Mock(
        side_effect=[RuntimeError("optional endpoint failed"), {"id": "good"}]
    )
    client.get_device_channels = Mock(side_effect=[[], [{"channel": 1}]])
    client.transformer.transform_device_data = Mock(
        side_effect=[None, {"api_device_id": "good", "firmware": "3.0"}]
    )

    assert client.poll_all_devices() == {"good": {"api_device_id": "good", "firmware": "3.0"}}

    client.get_devices = Mock(side_effect=SennheiserAPIError("list unavailable"))
    assert client.poll_all_devices() == {}

    client.get_devices = Mock(return_value=[{"id": "missing-firmware"}])
    client.get_device = Mock(return_value={"id": "missing-firmware"})
    client._enrich_device_data = Mock(return_value={"id": "missing-firmware"})
    client.get_device_channels = Mock(return_value=[])
    client.transformer.transform_device_data = Mock(
        return_value={"api_device_id": "missing-firmware", "firmware": ""}
    )
    assert "missing-firmware" in client.poll_all_devices()
