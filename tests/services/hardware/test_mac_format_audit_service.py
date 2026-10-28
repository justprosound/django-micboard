"""Read-only census of stored chassis MAC address formats."""

from io import StringIO

from django.core.management import call_command

import pytest

from micboard.services.hardware.mac_format_audit_service import MacFormatAuditService
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db

EMPTY = {"total": 0, "canonical": 0, "legacy": 0, "unmatched": 0, "invalid": 0, "blank": 0}


def _chassis(mac: str | None, secondary: str = "") -> None:
    WirelessChassisFactory(mac_address=mac, mac_address_secondary=secondary)


def test_an_empty_table_reports_zero_everywhere() -> None:
    result = MacFormatAuditService.audit()

    assert result.primary.model_dump() == EMPTY
    assert result.secondary.model_dump() == EMPTY


def test_each_stored_format_is_counted_once() -> None:
    _chassis("02:00:00:00:00:01")  # canonical
    _chassis("02-00-00-00-00-02")  # legacy: hyphenated
    _chassis("020000000003")  # legacy: compact
    _chassis("02:00:00:00:00:0A")  # legacy: upper case
    _chassis("not-a-mac")  # invalid
    _chassis("")  # blank
    _chassis(None)  # blank

    primary = MacFormatAuditService.audit().primary

    assert primary.model_dump() == {
        "total": 7,
        "canonical": 1,
        "legacy": 3,
        "unmatched": 0,
        "invalid": 1,
        "blank": 2,
    }


def test_valid_values_the_queries_cannot_match_are_not_called_legacy() -> None:
    """Mixed-case and padded values sit outside the six variants the lookups try."""
    _chassis("02:00:00:00:00:0a")  # canonical
    _chassis("02:00:00:00:00:0A")  # legacy: upper case, a queried variant
    _chassis("Aa:00:00:00:00:01")  # mixed case: no query variant matches
    _chassis(" 02:00:00:00:00:02")  # padded: no query variant matches

    primary = MacFormatAuditService.audit().primary

    assert (primary.canonical, primary.legacy, primary.unmatched) == (1, 1, 2)


def test_the_secondary_address_is_counted_separately() -> None:
    _chassis("02:00:00:00:00:01", secondary="02-00-00-00-00-09")
    _chassis("02:00:00:00:00:02")

    result = MacFormatAuditService.audit()

    assert (result.primary.legacy, result.primary.canonical) == (0, 2)
    assert (result.secondary.legacy, result.secondary.blank) == (1, 1)


def test_the_command_prints_totals_and_never_an_address() -> None:
    _chassis("02-00-00-00-00-02", secondary="02-00-00-00-00-07")
    out = StringIO()

    call_command("audit_mac_formats", stdout=out)

    text = out.getvalue()
    assert "mac_address (total: 1)" in text
    assert "mac_address_secondary (total: 1)" in text
    assert "legacy: 1" in text
    for leaked in ("02-00-00-00-00-02", "02:00:00:00:00:02", "02-00-00-00-00-07"):
        assert leaked not in text
