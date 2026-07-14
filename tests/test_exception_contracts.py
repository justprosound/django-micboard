"""Public exception payload and message contracts."""

from micboard.exceptions import (
    APIError,
    DiscoveryError,
    HardwareNotFoundError,
    HardwareValidationError,
    LocationAlreadyExistsError,
    LocationNotFoundError,
    ManufacturerNotSupportedError,
    MicboardError,
    ServiceError,
)


def test_base_error_exposes_code_message_and_details() -> None:
    """Structured errors retain machine-readable and human-readable context."""
    error = MicboardError("broken", code="BROKEN", details={"item": 1})

    assert str(error) == "[BROKEN] broken"
    assert error.message == "broken"
    assert error.code == "BROKEN"
    assert error.details == {"item": 1}
    assert MicboardError("plain").details == {}


def test_domain_errors_build_stable_payloads() -> None:
    """Domain-specific constructors populate stable codes and details."""
    unsupported = ManufacturerNotSupportedError("vendor")
    assert unsupported.details == {"manufacturer": "vendor"}

    missing = HardwareNotFoundError("device-1", "vendor")
    assert missing.details == {"device_id": "device-1", "manufacturer": "vendor"}
    assert "for manufacturer 'vendor'" in str(missing)

    missing_without_vendor = HardwareNotFoundError("device-2")
    assert missing_without_vendor.details == {"device_id": "device-2"}

    invalid = HardwareValidationError("ip", "invalid")
    assert invalid.details == {"field": "ip", "message": "invalid"}

    api = APIError("unavailable", status_code=503, response_body="retry")
    assert api.details == {"status_code": 503, "response": "retry"}

    location = LocationNotFoundError(7)
    assert location.details == {"location_id": 7}

    service = ServiceError("poller", "sync", "timeout")
    assert service.details == {"service": "poller", "operation": "sync"}


def test_marker_errors_accept_base_contract() -> None:
    """Marker subclasses remain fully usable structured exceptions."""
    for error_type in (DiscoveryError, LocationAlreadyExistsError):
        error = error_type("failed", code="DOMAIN")
        assert isinstance(error, MicboardError)
        assert str(error) == "[DOMAIN] failed"
