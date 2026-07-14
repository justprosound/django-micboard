"""RF channel regulatory and lifecycle service contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError

import pytest

from micboard.services.hardware.rf_channel_service import (
    finalize_channel_save,
    get_needs_regulatory_update,
    get_regulatory_domain,
    get_regulatory_domain_for_location,
    get_regulatory_status,
    has_regulatory_coverage,
    is_receive_channel,
    is_send_channel,
    prepare_channel_for_save,
)
from tests.factories.rf_coordination import RFChannelFactory

pytestmark = pytest.mark.django_db


def test_location_domain_resolution_handles_absent_context_and_explicit_domain() -> None:
    """Location resolution prefers explicit building policy and tolerates missing context."""
    domain = object()

    assert get_regulatory_domain_for_location(None) is None
    assert get_regulatory_domain_for_location(SimpleNamespace(building=None)) is None
    assert (
        get_regulatory_domain_for_location(
            SimpleNamespace(building=SimpleNamespace(regulatory_domain=domain, country="US"))
        )
        is domain
    )


def test_location_domain_resolution_falls_back_to_country_lookup() -> None:
    """Country codes provide the fallback when a building has no explicit domain."""
    domain = object()
    queryset = Mock()
    queryset.first.return_value = domain
    with patch(
        "micboard.models.rf_coordination.compliance.RegulatoryDomain.objects.filter",
        return_value=queryset,
    ) as filter_:
        result = get_regulatory_domain_for_location(
            SimpleNamespace(building=SimpleNamespace(regulatory_domain=None, country="us"))
        )

    assert result is domain
    filter_.assert_called_once_with(country_code="US")
    assert (
        get_regulatory_domain_for_location(
            SimpleNamespace(building=SimpleNamespace(regulatory_domain=None, country=""))
        )
        is None
    )


def test_channel_domain_delegates_through_chassis_location() -> None:
    """RF channels use their chassis location as regulatory context."""
    domain = object()
    channel = SimpleNamespace(
        chassis=SimpleNamespace(
            location=SimpleNamespace(
                building=SimpleNamespace(regulatory_domain=domain, country="US")
            )
        )
    )

    assert get_regulatory_domain(SimpleNamespace(chassis=None)) is None
    assert get_regulatory_domain(channel) is domain


def test_regulatory_coverage_requires_domain_frequency_and_global_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coverage fails closed outside global domain bounds."""
    domain = SimpleNamespace(min_frequency_mhz=470.0, max_frequency_mhz=608.0)
    monkeypatch.setattr(
        "micboard.services.hardware.rf_channel_service.get_regulatory_domain",
        Mock(side_effect=[None, domain, domain, domain]),
    )

    assert has_regulatory_coverage(SimpleNamespace(frequency=500.0)) is False
    assert has_regulatory_coverage(SimpleNamespace(frequency=None)) is False
    assert has_regulatory_coverage(SimpleNamespace(frequency=500.0)) is True
    assert has_regulatory_coverage(SimpleNamespace(frequency=700.0)) is False


def test_regulatory_update_applies_only_to_active_configured_uncovered_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin attention excludes inactive and unconfigured RF resources."""
    coverage = Mock(side_effect=[True, False])
    monkeypatch.setattr(
        "micboard.services.hardware.rf_channel_service.has_regulatory_coverage",
        coverage,
    )

    assert (
        get_needs_regulatory_update(SimpleNamespace(resource_state="free", frequency=500.0))
        is False
    )
    assert (
        get_needs_regulatory_update(SimpleNamespace(resource_state="active", frequency=None))
        is False
    )
    assert (
        get_needs_regulatory_update(SimpleNamespace(resource_state="reserved", frequency=500.0))
        is False
    )
    assert (
        get_needs_regulatory_update(SimpleNamespace(resource_state="active", frequency=700.0))
        is True
    )


@pytest.mark.parametrize(
    ("domain", "frequency", "coverage", "message"),
    [
        (None, 500.0, False, "No regulatory domain"),
        (SimpleNamespace(code="FCC"), None, False, "No operating frequency"),
        (SimpleNamespace(code="FCC"), 700.0, False, "not covered by FCC"),
        (SimpleNamespace(code="FCC"), 500.0, True, "coverage OK (FCC)"),
    ],
)
def test_regulatory_status_explains_coverage_state(
    domain: object | None,
    frequency: float | None,
    coverage: bool,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin status payloads explain every coverage outcome."""
    channel = SimpleNamespace(frequency=frequency, resource_state="active")
    monkeypatch.setattr(
        "micboard.services.hardware.rf_channel_service.get_regulatory_domain",
        Mock(return_value=domain),
    )
    monkeypatch.setattr(
        "micboard.services.hardware.rf_channel_service.has_regulatory_coverage",
        Mock(return_value=coverage),
    )
    monkeypatch.setattr(
        "micboard.services.hardware.rf_channel_service.get_needs_regulatory_update",
        Mock(return_value=not coverage),
    )

    result = get_regulatory_status(channel)

    assert message in str(result["message"])
    assert result["regulatory_domain"] == (domain.code if domain else None)
    assert result["has_coverage"] is coverage


@pytest.mark.parametrize(
    ("direction", "receive", "send"),
    [
        ("receive", True, False),
        ("send", False, True),
        ("bidirectional", True, True),
        ("unknown", False, False),
    ],
)
def test_channel_direction_predicates(
    direction: str,
    receive: bool,
    send: bool,
) -> None:
    """Direction predicates remain symmetric for bidirectional resources."""
    channel = SimpleNamespace(link_direction=direction)
    assert is_receive_channel(channel) is receive
    assert is_send_channel(channel) is send


def test_new_channel_validation_accepts_capacity_and_wmas_overcommit() -> None:
    """Ordinary channels honor capacity while WMAS chassis may exceed fixed slots."""
    chassis = SimpleNamespace(
        wmas_capable=False,
        model="RX-4",
        get_expected_channel_count=Mock(return_value=4),
    )
    channel = SimpleNamespace(
        _state=SimpleNamespace(adding=True),
        chassis=chassis,
        channel_number=4,
    )

    assert prepare_channel_for_save(channel) == {
        "old_resource_state": None,
        "state_changed": False,
        "update_fields": set(),
    }

    channel.channel_number = 5
    with pytest.raises(ValidationError, match="exceeds RX-4 capacity"):
        prepare_channel_for_save(channel)

    chassis.wmas_capable = True
    assert prepare_channel_for_save(channel)["state_changed"] is False
    channel.channel_number = 0
    with pytest.raises(ValidationError, match="at least 1"):
        prepare_channel_for_save(channel)


def test_existing_channel_disable_derives_valid_state_transition() -> None:
    """Disabling an enabled channel atomically moves its resource state to disabled."""
    channel = RFChannelFactory(resource_state="free", enabled=True)
    channel.enabled = False

    context = prepare_channel_for_save(channel)

    assert channel.resource_state == "disabled"
    assert context == {
        "old_resource_state": "free",
        "state_changed": True,
        "update_fields": {"resource_state"},
    }


def test_existing_channel_allows_unchanged_and_rejects_invalid_transition() -> None:
    """No-op states pass while lifecycle-invalid transitions are rejected."""
    channel = RFChannelFactory(resource_state="active", enabled=True)
    assert prepare_channel_for_save(channel)["state_changed"] is False

    channel.resource_state = "reserved"
    with pytest.raises(ValueError, match="active → reserved"):
        prepare_channel_for_save(channel)

    type(channel).objects.filter(pk=channel.pk).update(resource_state="terminal")
    channel.resource_state = "active"
    with pytest.raises(ValueError, match="Allowed: none"):
        prepare_channel_for_save(channel)


def test_finalize_channel_save_logs_only_state_changes() -> None:
    """Audit logging is emitted once for an actual persisted state transition."""
    channel = SimpleNamespace(resource_state="active")
    with patch("micboard.services.maintenance.audit.AuditService.log_activity") as log:
        finalize_channel_save(channel, {"state_changed": False})
        finalize_channel_save(
            channel,
            {"state_changed": True, "old_resource_state": "reserved"},
        )

    log.assert_called_once()
    assert log.call_args.kwargs["old_values"] == {"resource_state": "reserved"}
    assert log.call_args.kwargs["new_values"] == {"resource_state": "active"}
