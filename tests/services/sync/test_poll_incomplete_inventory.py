"""A vendor response the integration client had to trim never reads as absent chassis."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.integrations.sennheiser.device_client import SennheiserDeviceClient
from micboard.integrations.shure.device_client import ShureDeviceClient
from micboard.models.monitoring.alert import Alert
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.manufacturer.sync import ManufacturerSyncService
from tests.fake_vendor import use_vendor

pytestmark = pytest.mark.django_db


class _ClientBackedVendor:
    """A vendor whose inventory is whatever a real integration client makes of a response."""

    def __init__(self, get_devices: object) -> None:
        self.get_devices = get_devices

    @staticmethod
    def normalize_device(raw: dict[str, object]) -> NormalizedChassis:
        return NormalizedChassis(
            api_device_id=str(raw["id"]), ip=str(raw["ipAddress"]), serial_number="present-1"
        )

    @staticmethod
    def get_device_channels(device_id: str) -> list[dict[str, object]]:
        return []

    @staticmethod
    def normalize_channels(api_channels: list[dict[str, object]]) -> list[object]:
        return []


_SHURE_DEVICE = {
    "hardwareIdentity": {"deviceId": "present", "serialNumber": "present-1"},
    "communicationProtocol": {"address": "192.0.2.10"},
}
_SENNHEISER_DEVICE = {"id": "present", "ipAddress": "192.0.2.10"}


@pytest.mark.parametrize(
    ("client_class", "response"),
    [
        pytest.param(
            ShureDeviceClient,
            {"edges": [{"node": _SHURE_DEVICE}, {"cursor": "no-node"}]},
            id="shure-edge-without-node",
        ),
        pytest.param(ShureDeviceClient, [_SHURE_DEVICE, "not-a-device"], id="shure-non-dict-item"),
        pytest.param(
            ShureDeviceClient,
            [_SHURE_DEVICE, {"communicationProtocol": {"address": "192.0.2.77"}}],
            id="shure-device-without-id",
        ),
        pytest.param(ShureDeviceClient, {"unexpected": "shape"}, id="shure-unknown-shape"),
        pytest.param(
            SennheiserDeviceClient, [_SENNHEISER_DEVICE, 7], id="sennheiser-non-dict-item"
        ),
        pytest.param(
            SennheiserDeviceClient, {"unexpected": "shape"}, id="sennheiser-unknown-shape"
        ),
    ],
)
def test_a_vendor_response_the_client_had_to_trim_never_takes_a_chassis_offline(
    monkeypatch: pytest.MonkeyPatch,
    watched: SimpleNamespace,
    client_class: type,
    response: object,
) -> None:
    """A shorter inventory from a partly malformed response is not proof a chassis is gone."""
    client = client_class(Mock(_make_request=Mock(return_value=response)))
    use_vendor(monkeypatch, _ClientBackedVendor(client.get_devices))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert result.devices_removed == 0
    assert watched.chassis.status == "online"
    assert not Alert.objects.exists()


@pytest.mark.parametrize(
    ("client_class", "response"),
    [
        (ShureDeviceClient, {"edges": [{"node": _SHURE_DEVICE}]}),
        (SennheiserDeviceClient, [_SENNHEISER_DEVICE]),
    ],
)
def test_a_cleanly_read_vendor_response_still_reconciles(
    monkeypatch: pytest.MonkeyPatch,
    watched: SimpleNamespace,
    client_class: type,
    response: object,
) -> None:
    """The clients mark an inventory incomplete only when they dropped something."""
    client = client_class(Mock(_make_request=Mock(return_value=response)))
    use_vendor(monkeypatch, _ClientBackedVendor(client.get_devices))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert result.devices_removed == 1
    assert watched.chassis.status == "offline"
