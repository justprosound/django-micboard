"""Behavior and failure-path coverage for the EFIS import service."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from django.utils import timezone

import httpx
import pytest

from micboard.services.maintenance import efis_import as efis_module
from micboard.services.maintenance.efis_import import EFISImportService


def test_efis_last_import_and_staleness(monkeypatch) -> None:
    query = MagicMock()
    monkeypatch.setattr(efis_module.ActivityLog.objects, "filter", Mock(return_value=query))
    query.order_by.return_value = query
    query.first.return_value = None
    assert EFISImportService.get_last_import_date() is None
    assert EFISImportService.is_outdated() is True

    recent = timezone.now() - timedelta(days=1)
    query.first.return_value = SimpleNamespace(created_at=recent)
    assert EFISImportService.get_last_import_date() == recent
    assert EFISImportService.is_outdated(days_threshold=30) is False
    query.first.return_value = SimpleNamespace(created_at=timezone.now() - timedelta(days=31))
    assert EFISImportService.is_outdated(days_threshold=30) is True


def test_efis_import_success_skips_aggregate_regions_and_counts_bands(monkeypatch) -> None:
    session = MagicMock(spec=httpx.Client)
    monkeypatch.setattr(efis_module, "create_resilient_session", Mock(return_value=session))
    activity_create = Mock()
    monkeypatch.setattr(efis_module.ActivityLog.objects, "create", activity_create)
    monkeypatch.setattr(EFISImportService, "_fetch_wireless_term_ids", Mock(return_value={1}))
    monkeypatch.setattr(
        EFISImportService,
        "_fetch_regions",
        Mock(
            return_value=[
                {"id": 1, "regionCode": "ECA", "name": "Aggregate"},
                {"id": 2, "regionCode": "gb", "name": "United Kingdom"},
            ]
        ),
    )
    domain = object()
    update_domain = Mock(return_value=(domain, True))
    monkeypatch.setattr(efis_module.RegulatoryDomain.objects, "update_or_create", update_domain)
    monkeypatch.setattr(
        EFISImportService,
        "_sync_region_application_bands",
        Mock(return_value=(2, 3)),
    )

    result = EFISImportService.run_import(user="operator")

    assert result == {
        "success": True,
        "message": "Import completed successfully",
        "domains_updated": 1,
        "bands_created": 2,
        "bands_updated": 3,
    }
    assert update_domain.call_args.kwargs["code"] == "GB"
    assert update_domain.call_args.kwargs["defaults"]["country_code"] == "GB"
    assert activity_create.call_count == 2
    session.close.assert_called_once_with()


def test_efis_import_records_failure_and_closes_session(monkeypatch) -> None:
    session = MagicMock(spec=httpx.Client)
    monkeypatch.setattr(efis_module, "create_resilient_session", Mock(return_value=session))
    activity_create = Mock()
    monkeypatch.setattr(efis_module.ActivityLog.objects, "create", activity_create)
    monkeypatch.setattr(
        EFISImportService,
        "_fetch_wireless_term_ids",
        Mock(side_effect=RuntimeError("EFIS offline")),
    )

    result = EFISImportService.run_import()

    assert result == {
        "success": False,
        "message": "EFIS import failed (RuntimeError); details redacted.",
    }
    assert "EFIS offline" not in str(result)
    assert activity_create.call_args_list[-1].kwargs["status"] == "failed"
    assert "EFIS offline" not in str(activity_create.call_args_list[-1])
    session.close.assert_called_once_with()


def test_efis_payload_helpers_and_band_sync(monkeypatch) -> None:
    response = Mock()
    response.json.return_value = {"regions": [{"id": 1}]}
    monkeypatch.setattr(EFISImportService, "_request_json", Mock(return_value=response.json()))
    assert EFISImportService._fetch_regions(Mock()) == [{"id": 1}]

    EFISImportService._request_json.return_value = {
        "terms": [
            {"id": 1, "name": "Radio microphones"},
            {"id": 2, "name": "Broadcast"},
            {"id": "bad", "name": "PMSE"},
        ]
    }
    assert EFISImportService._fetch_wireless_term_ids(Mock()) == {1}
    EFISImportService._request_json.return_value = {"terms": []}
    with pytest.raises(ValueError, match="no wireless-related terms"):
        EFISImportService._fetch_wireless_term_ids(Mock())

    applications = [
        {"applicationTerm": {"id": 1, "name": "PMSE"}, "comment": "Licensed"},
        {"applicationTerm": {"id": 9, "name": "Broadcast"}},
    ]
    EFISImportService._request_json.return_value = {
        "applicationRanges": [
            {"applications": [], "low": 1, "high": 2},
            {"applications": applications, "low": 470_000_000, "high": 478_000_000},
            {"applications": applications, "low": 480_000_000, "high": 488_000_000},
        ]
    }
    update_band = Mock(side_effect=[(object(), True), (object(), False)])
    monkeypatch.setattr(efis_module.FrequencyBand.objects, "update_or_create", update_band)
    assert EFISImportService._sync_region_application_bands(
        session=Mock(),
        domain=object(),  # type: ignore[arg-type]
        region_id=1,
        region_name="Region",
        wireless_term_ids={1},
    ) == (1, 1)
    assert update_band.call_args_list[0].kwargs["start_frequency_mhz"] == 470.0


def test_efis_request_retries_then_returns_and_raises(monkeypatch) -> None:
    request = httpx.Request("GET", "https://efis.test")
    good_response = Mock()
    good_response.raise_for_status.return_value = None
    good_response.json.return_value = {"ok": True}
    session = Mock()
    session.get.side_effect = [httpx.ConnectError("down", request=request), good_response]
    sleep = Mock()
    monkeypatch.setattr(efis_module.time, "sleep", sleep)
    assert EFISImportService._request_json(session=session, path="/test") == {"ok": True}
    sleep.assert_called_once_with(1.0)

    session.get.side_effect = [httpx.ConnectError("down", request=request)] * 3
    with pytest.raises(RuntimeError, match="EFIS request failed") as exc_info:
        EFISImportService._request_json(session=session, path="/test", params={"id": 1})
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)
    assert "down" not in str(exc_info.value)


def test_efis_value_helpers_cover_fallbacks_and_deduplication() -> None:
    by_id = {"applicationTerm": {"id": 1, "name": "Other"}}
    by_name = {"applicationTerm": {"id": 9, "name": "PMSE audio"}}
    unrelated = {"applicationTerm": {"id": 9, "name": "Broadcast"}}
    assert EFISImportService._matches_wireless_application(by_id, {1}) is True
    assert EFISImportService._matches_wireless_application(by_name, {1}) is True
    assert EFISImportService._matches_wireless_application(unrelated, {1}) is False
    applications = [
        {"applicationTerm": {"name": "PMSE"}, "comment": " one "},
        {"applicationTerm": {"name": "Microphone"}, "comment": "one"},
        {"applicationTerm": {}, "comment": ""},
    ]
    assert EFISImportService._build_band_name(applications) == (
        "Microphone, PMSE, Wireless audio (EFIS)"
    )
    assert EFISImportService._build_band_name([]) == "Wireless audio (EFIS)"
    assert EFISImportService._combine_comments(applications) == "one"
    assert "Comments: one" in EFISImportService._build_description(
        region_name="Region", applications=applications
    )
    assert EFISImportService._build_description(region_name="Region", applications=[]) == (
        "EFIS application range for Region."
    )
    assert EFISImportService._hz_to_mhz(470_123_456) == 470.123456
    assert EFISImportService._normalize_country_code("") == ""
    assert EFISImportService._normalize_country_code(" gb ") == "GB"
    assert EFISImportService._normalize_country_code("GBR") == ""
