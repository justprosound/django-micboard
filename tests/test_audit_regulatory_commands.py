"""Behavioral coverage for audit maintenance commands."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.management.commands import archive_audit_logs
from micboard.management.commands import audit_regulatory_coverage as regulatory_command


class _Query(list):
    def count(self):
        return len(self)

    def select_related(self, *_fields):
        return self

    def exists(self):
        return bool(self)

    def filter(self, **_filters):
        return self

    def order_by(self, *_fields):
        return self


@pytest.mark.parametrize("activity_only", [True, False])
def test_archive_command_delegates_retention_work(monkeypatch, activity_only: bool) -> None:
    command = archive_audit_logs.Command(stdout=StringIO())
    archive = Mock(return_value={"archived": 2, "file": "archive.csv"})
    prune_sync = Mock(return_value=3)
    prune_health = Mock(return_value=4)
    monkeypatch.setattr(archive_audit_logs.AuditService, "archive_activity_logs", archive)
    monkeypatch.setattr(archive_audit_logs.AuditService, "prune_service_sync_logs", prune_sync)
    monkeypatch.setattr(archive_audit_logs.AuditService, "prune_api_health_logs", prune_health)

    command.handle(retention_days=12, activity_only=activity_only)

    archive.assert_called_once_with(retention_days=12)
    if activity_only:
        prune_sync.assert_not_called()
        prune_health.assert_not_called()
    else:
        prune_sync.assert_called_once_with(retention_days=12)
        prune_health.assert_called_once_with(retention_days=12)
    assert "Archived 2 activity logs" in command.stdout._out.getvalue()


def _chassis(name: str, *, model: str = "AD4Q"):
    return SimpleNamespace(
        name=name,
        model=model,
        location="Rack",
        band_plan_name="G50",
        save=Mock(),
    )


def test_regulatory_chassis_audit_reports_all_outcomes(monkeypatch) -> None:
    chassis = [_chassis(name) for name in ("domain", "plan", "coverage", "ok")]
    monkeypatch.setattr(
        regulatory_command.WirelessChassis.objects,
        "filter",
        Mock(return_value=_Query(chassis)),
    )
    statuses = iter(
        [
            {"regulatory_domain": None, "has_band_plan": False, "has_coverage": False},
            {"regulatory_domain": "US", "has_band_plan": False, "has_coverage": False},
            {
                "regulatory_domain": "US",
                "has_band_plan": True,
                "has_coverage": False,
                "band_plan_range": "470-534",
            },
            {"regulatory_domain": "US", "has_band_plan": True, "has_coverage": True},
        ]
    )
    monkeypatch.setattr(
        regulatory_command, "get_band_plan_regulatory_status", lambda _item: next(statuses)
    )
    output = StringIO()
    command = regulatory_command.Command(stdout=output)

    command.audit_chassis(False)

    text = output.getvalue()
    assert "Missing Regulatory Domain: 1" in text
    assert "Missing Band Plan: 1" in text
    assert "Missing Coverage: 1" in text


@pytest.mark.parametrize("detected", [True, False])
def test_regulatory_chassis_fix_mode(monkeypatch, detected: bool) -> None:
    chassis = _chassis("receiver")
    monkeypatch.setattr(
        regulatory_command.WirelessChassis.objects,
        "filter",
        Mock(return_value=_Query([chassis])),
    )
    monkeypatch.setattr(
        regulatory_command,
        "get_band_plan_regulatory_status",
        Mock(
            return_value={
                "regulatory_domain": "US",
                "has_band_plan": False,
                "has_coverage": False,
            }
        ),
    )
    monkeypatch.setattr(regulatory_command, "apply_detected_band_plan", Mock(return_value=detected))
    output = StringIO()
    command = regulatory_command.Command(stdout=output)

    command.audit_chassis(True)

    if detected:
        chassis.save.assert_called_once_with()
        assert "Auto-Fixed Band Plans: 1" in output.getvalue()
    else:
        chassis.save.assert_not_called()
        assert "Missing Band Plan: 1" in output.getvalue()


def test_regulatory_channel_audit_and_handle(monkeypatch) -> None:
    channels = [
        SimpleNamespace(frequency=500.0),
        SimpleNamespace(frequency=510.0),
    ]
    monkeypatch.setattr(
        regulatory_command.RFChannel.objects,
        "filter",
        Mock(return_value=_Query(channels)),
    )
    statuses = iter(
        [
            {"has_coverage": False, "regulatory_domain": None},
            {"has_coverage": True, "regulatory_domain": "US"},
        ]
    )
    monkeypatch.setattr(
        "micboard.services.hardware.rf_channel_service.get_regulatory_status",
        lambda _channel: next(statuses),
    )
    output = StringIO()
    command = regulatory_command.Command(stdout=output)
    command.audit_chassis = Mock()

    command.handle(fix=True)

    command.audit_chassis.assert_called_once_with(True)
    assert "Channels with Non-Compliant/Unknown Frequencies: 1" in output.getvalue()
