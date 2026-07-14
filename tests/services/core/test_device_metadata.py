"""Manufacturer-specific discovered-device metadata contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from micboard.services.core.device_metadata import (
    DeviceMetadataAccessor,
    GenericMetadataAccessor,
    SennheiserMetadataAccessor,
    ShureMetadataAccessor,
)


class _ConcreteAccessor(DeviceMetadataAccessor):
    """Concrete probe used to verify the abstract fallback contract."""

    def get_compatibility_status(self) -> str | None:
        return super().get_compatibility_status()

    def get_device_state(self) -> str | None:
        return super().get_device_state()

    def get_incompatibility_reason(self) -> str | None:
        return super().get_incompatibility_reason()


def test_abstract_accessor_requires_contract_implementation() -> None:
    """The base strategy cannot be instantiated without all metadata operations."""
    with pytest.raises(TypeError):
        DeviceMetadataAccessor()

    accessor = _ConcreteAccessor()
    assert accessor.data == {}
    assert accessor.get_compatibility_status() is None
    assert accessor.get_device_state() is None
    assert accessor.get_incompatibility_reason() is None


@pytest.mark.parametrize(
    ("manufacturer", "expected_type"),
    [
        (None, GenericMetadataAccessor),
        (object(), GenericMetadataAccessor),
        (SimpleNamespace(code="SHURE"), ShureMetadataAccessor),
        (SimpleNamespace(code="sennheiser"), SennheiserMetadataAccessor),
        (SimpleNamespace(code="other"), GenericMetadataAccessor),
    ],
)
def test_accessor_factory_selects_strategy(manufacturer: object, expected_type: type) -> None:
    """Manufacturer codes select a strategy while unknown sources remain readable."""
    metadata = {"state": "ONLINE"}

    accessor = DeviceMetadataAccessor.get_for(manufacturer, metadata)  # type: ignore[arg-type]

    assert isinstance(accessor, expected_type)
    assert accessor.data is metadata


def test_generic_accessor_reads_common_metadata_shapes() -> None:
    """Generic metadata supports both documented device-state keys."""
    primary = GenericMetadataAccessor(
        {
            "compatibility": "COMPATIBLE",
            "state": "ONLINE",
            "device_state": "OFFLINE",
            "incompatibility_reason": "Unsupported",
        }
    )
    fallback = GenericMetadataAccessor({"device_state": "DISCOVERED"})

    assert primary.get_compatibility_status() == "COMPATIBLE"
    assert primary.get_device_state() == "ONLINE"
    assert primary.get_incompatibility_reason() == "Unsupported"
    assert fallback.get_device_state() == "DISCOVERED"
    assert GenericMetadataAccessor().get_device_state() is None


@pytest.mark.parametrize(
    ("compatibility", "metadata", "expected"),
    [
        (
            "INCOMPATIBLE_TOO_OLD",
            {"model": "RX-1"},
            "Upgrade RX-1 firmware to interact via API.",
        ),
        (
            "INCOMPATIBLE_TOO_OLD",
            {},
            "Upgrade device firmware to interact via API.",
        ),
        (
            "INCOMPATIBLE_TOO_NEW",
            {},
            "Upgrade the API to interact with this device.",
        ),
        (
            "UNKNOWN",
            {},
            "Device is incompatible with current API version (status: UNKNOWN).",
        ),
        (
            None,
            {},
            "Device is incompatible with current API version (status: None).",
        ),
        ("COMPATIBLE", {}, None),
    ],
)
def test_shure_incompatibility_messages_explain_remediation(
    compatibility: str | None,
    metadata: dict[str, str],
    expected: str | None,
) -> None:
    """Shure compatibility states produce operator-facing remediation."""
    accessor = ShureMetadataAccessor({"compatibility": compatibility, **metadata})

    reason = accessor.get_incompatibility_reason()

    if expected is None:
        assert reason is None
    else:
        assert expected in reason


def test_shure_state_and_protocol_handle_structured_and_invalid_payloads() -> None:
    """Protocol extraction tolerates absent and unexpectedly shaped API values."""
    accessor = ShureMetadataAccessor(
        {
            "deviceState": "ONLINE",
            "communicationProtocol": {"name": "Shure Link"},
        }
    )

    assert accessor.get_device_state() == "ONLINE"
    assert accessor.get_communication_protocol() == "Shure Link"
    assert (
        ShureMetadataAccessor({"communicationProtocol": "invalid"}).get_communication_protocol()
        is None
    )


def test_sennheiser_metadata_exposes_state_versions_and_compatibility() -> None:
    """Sennheiser metadata supports state fallbacks and version diagnostics."""
    accessor = SennheiserMetadataAccessor(
        {
            "compatibility_status": "INCOMPATIBLE",
            "status": "OFFLINE",
            "required_api_version": "2.1",
            "hardware_version": "A",
            "software_version": "1.5",
        }
    )

    assert accessor.get_compatibility_status() == "INCOMPATIBLE"
    assert accessor.get_device_state() == "OFFLINE"
    assert accessor.get_incompatibility_reason() == "Device requires API version 2.1 or higher."
    assert accessor.get_hardware_version() == "A"
    assert accessor.get_software_version() == "1.5"

    without_version = SennheiserMetadataAccessor({"compatibility_status": "INCOMPATIBLE"})
    assert without_version.get_incompatibility_reason() == (
        "Device is incompatible with current API version."
    )
    assert (
        SennheiserMetadataAccessor(
            {"compatibility_status": "COMPATIBLE"}
        ).get_incompatibility_reason()
        is None
    )
    assert (
        SennheiserMetadataAccessor({"state": "ONLINE", "status": "OFFLINE"}).get_device_state()
        == "ONLINE"
    )
