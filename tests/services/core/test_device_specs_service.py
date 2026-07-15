"""Device specification lookup and application contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from micboard.services.core.device_specs import DeviceSpec, DeviceSpecService


def test_spec_lookup_requires_manufacturer_and_model() -> None:
    """Incomplete device identity cannot select a specification."""
    manufacturer = SimpleNamespace(code="shure")

    assert DeviceSpecService.get_specs(None, "ULXD4D") is None
    assert DeviceSpecService.get_specs(manufacturer, "") is None


def test_spec_lookup_returns_registered_capabilities() -> None:
    """Known model aliases resolve channel and Dante capabilities."""
    spec = DeviceSpecService.get_specs(SimpleNamespace(code="SHURE"), "ULXD4D")

    assert spec == DeviceSpec(
        max_channels=2,
        dante_capable=True,
        model="ULXD4D",
        manufacturer="shure",
    )
    assert repr(spec) == "DeviceSpec(ULXD4D, channels=2, dante=True)"


def test_unknown_model_has_no_specification() -> None:
    """Unknown models do not manufacture a misleading four-channel specification."""
    assert (
        DeviceSpecService.get_specs(
            SimpleNamespace(code="shure"),
            "UNKNOWN-MODEL",
        )
        is None
    )
    assert DeviceSpecService.get_specs(object(), "UNKNOWN-MODEL") is None


def test_spec_lookup_contains_registry_failures() -> None:
    """Registry read errors leave callers free to preserve explicit device metadata."""
    with patch(
        "micboard.models.device_specs.get_device_spec",
        side_effect=RuntimeError("registry unavailable"),
    ):
        assert (
            DeviceSpecService.get_specs(
                SimpleNamespace(code="shure"),
                "ULXD4D",
            )
            is None
        )


def test_apply_specs_updates_known_model() -> None:
    """Known registry capabilities replace provisional chassis values."""
    chassis = SimpleNamespace(
        manufacturer=SimpleNamespace(code="shure"),
        model="ULXD4D",
        max_channels=8,
        dante_capable=False,
    )

    DeviceSpecService.apply_specs_to_chassis(chassis)

    assert chassis.max_channels == 2
    assert chassis.dante_capable is True


def test_apply_specs_preserves_explicit_unknown_model_capabilities() -> None:
    """Discovery metadata survives when the local registry has no matching model."""
    chassis = SimpleNamespace(
        manufacturer=SimpleNamespace(code="vendor"),
        model="Unregistered Receiver",
        max_channels=8,
        dante_capable=True,
    )

    DeviceSpecService.apply_specs_to_chassis(chassis)

    assert chassis.max_channels == 8
    assert chassis.dante_capable is True
