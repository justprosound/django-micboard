"""Read-only census of stored chassis MAC address formats."""

from io import StringIO

from django.core.management import call_command

import pytest

from micboard.services.hardware.mac_format_audit_service import MacFormatAuditService
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _chassis(mac: str | None) -> None:
    WirelessChassisFactory(mac_address=mac)


def test_an_empty_table_reports_zero_everywhere() -> None:
    result = MacFormatAuditService.audit()

    assert result.model_dump() == {
        "total": 0,
        "canonical": 0,
        "legacy": 0,
        "invalid": 0,
        "blank": 0,
    }


def test_each_stored_format_is_counted_once() -> None:
    _chassis("02:00:00:00:00:01")  # canonical
    _chassis("02-00-00-00-00-02")  # legacy: hyphenated
    _chassis("020000000003")  # legacy: compact
    _chassis("02:00:00:00:00:0A")  # legacy: upper case
    _chassis("not-a-mac")  # invalid
    _chassis("")  # blank
    _chassis(None)  # blank

    result = MacFormatAuditService.audit()

    assert (result.total, result.canonical, result.legacy, result.invalid, result.blank) == (
        7,
        1,
        3,
        1,
        2,
    )


def test_the_command_prints_totals_and_never_an_address() -> None:
    _chassis("02-00-00-00-00-02")
    out = StringIO()

    call_command("audit_mac_formats", stdout=out)

    text = out.getvalue()
    assert "legacy: 1" in text
    assert "02-00-00-00-00-02" not in text
    assert "02:00:00:00:00:02" not in text
