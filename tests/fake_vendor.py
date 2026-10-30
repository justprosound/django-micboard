"""A vendor plugin double, so tests drive the public sync interfaces instead of private ones."""

from collections.abc import Callable, Sequence

import pytest

from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis

BUILD_PLUGIN = "micboard.services.manufacturer.sync.build_manufacturer_plugin"


class FakeVendorPlugin:
    """Reports one raw device per payload; a `None` payload is a device that cannot normalize."""

    def __init__(
        self,
        payloads: Sequence[NormalizedChassis | None] = (),
        *,
        before_get_devices: Callable[[], None] | None = None,
    ) -> None:
        self.payloads = list(payloads)
        self.before_get_devices = before_get_devices

    @property
    def raw_devices(self) -> list[dict[str, int]]:
        """The raw inventory the vendor reports."""
        return [{"index": index} for index in range(len(self.payloads))]

    def get_devices(self) -> list[dict[str, int]]:
        """Return the raw inventory, after the optional vendor-side effect."""
        if self.before_get_devices is not None:
            self.before_get_devices()
        return self.raw_devices

    def normalize_device(self, api_data: dict[str, int]) -> NormalizedChassis | None:
        """Look the payload up by the raw device's position."""
        return self.payloads[api_data["index"]]

    def get_device_channels(self, device_id: str) -> list[dict[str, int]]:
        """Report no channels."""
        return []

    def normalize_channels(self, api_channels: list[dict[str, int]]) -> list[NormalizedChannel]:
        """Normalize no channels."""
        return []


def use_vendor(monkeypatch: pytest.MonkeyPatch, plugin: object) -> None:
    """Make the poll build `plugin` for every manufacturer."""
    monkeypatch.setattr(BUILD_PLUGIN, lambda _manufacturer: plugin)
