"""Behavior and failure-path coverage for the EFIS import service."""

import gzip
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


@pytest.mark.django_db
def test_efis_import_success_skips_aggregate_regions_and_counts_bands(monkeypatch) -> None:
    session = MagicMock(spec=httpx.Client)
    monkeypatch.setattr(efis_module.httpx, "Client", Mock(return_value=session))
    activity_create = Mock()
    monkeypatch.setattr(efis_module.AuditService, "log_activity", activity_create)
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
    monkeypatch.setattr(efis_module.httpx, "Client", Mock(return_value=session))
    activity_create = Mock()
    monkeypatch.setattr(efis_module.AuditService, "log_activity", activity_create)
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


@pytest.mark.django_db
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
    domain = efis_module.RegulatoryDomain.objects.create(code="GB", name="United Kingdom")
    stale = efis_module.FrequencyBand.objects.create(
        regulatory_domain=domain,
        name="PMSE (EFIS)",
        start_frequency_mhz=470.0,
        end_frequency_mhz=790.0,
    )
    manual = efis_module.FrequencyBand.objects.create(
        regulatory_domain=domain,
        name="Manual entry",
        start_frequency_mhz=500.0,
        end_frequency_mhz=510.0,
    )
    assert EFISImportService._sync_region_application_bands(
        session=Mock(),
        domain=domain,
        region_id=1,
        region_name="Region",
        wireless_term_ids={1},
    ) == (2, 0)
    starts = set(domain.frequency_bands.values_list("start_frequency_mhz", flat=True))
    assert starts == {470.0, 480.0, 500.0}
    assert not efis_module.FrequencyBand.objects.filter(pk=stale.pk).exists()
    assert efis_module.FrequencyBand.objects.filter(pk=manual.pk).exists()


@pytest.mark.django_db
def test_efis_empty_answer_keeps_existing_bands(monkeypatch) -> None:
    """An answer listing no ranges is a bad response and must not delete a region's bands."""
    monkeypatch.setattr(
        EFISImportService, "_request_json", Mock(return_value={"applicationRanges": []})
    )
    domain = efis_module.RegulatoryDomain.objects.create(code="GB", name="United Kingdom")
    band = efis_module.FrequencyBand.objects.create(
        regulatory_domain=domain,
        name="PMSE (EFIS)",
        start_frequency_mhz=470.0,
        end_frequency_mhz=790.0,
    )

    assert EFISImportService._sync_region_application_bands(
        session=Mock(), domain=domain, region_id=1, region_name="Region", wireless_term_ids={1}
    ) == (0, 0)
    assert efis_module.FrequencyBand.objects.filter(pk=band.pk).exists()


def _efis_client(*responses: httpx.Response | Exception) -> tuple[httpx.Client, list[int]]:
    queue = list(responses)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_efis_request_retries_transient_errors_only(monkeypatch) -> None:
    sleep = Mock()
    monkeypatch.setattr(efis_module.time, "sleep", sleep)
    request = httpx.Request("GET", "https://efis.test")

    client, calls = _efis_client(
        httpx.ConnectError("down", request=request),
        httpx.Response(503),
        httpx.Response(200, json={"ok": True}),
    )
    assert EFISImportService._request_json(session=client, path="/test") == {"ok": True}
    assert len(calls) == 3

    client, calls = _efis_client(httpx.Response(404), httpx.Response(200, json={}))
    with pytest.raises(RuntimeError, match="EFIS request failed") as exc_info:
        EFISImportService._request_json(session=client, path="/test")
    assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
    assert len(calls) == 1

    client, calls = _efis_client(*[httpx.ConnectError("down", request=request)] * 3)
    with pytest.raises(RuntimeError, match="EFIS request failed"):
        EFISImportService._request_json(session=client, path="/test")
    assert len(calls) == 3


def test_efis_request_rejects_oversized_body(monkeypatch) -> None:
    monkeypatch.setattr(
        efis_module.HTTPClientLimits,
        "from_settings",
        Mock(
            return_value=efis_module.HTTPClientLimits(
                max_retry_delay_seconds=1, max_response_bytes=10
            )
        ),
    )
    client, calls = _efis_client(httpx.Response(200, content=b"x" * 11))
    with pytest.raises(RuntimeError, match="size limit"):
        EFISImportService._request_json(session=client, path="/test")
    assert len(calls) == 1


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


@pytest.mark.django_db
def test_efis_missing_ranges_key_raises_and_keeps_bands(monkeypatch) -> None:
    monkeypatch.setattr(EFISImportService, "_request_json", Mock(return_value={}))
    domain = efis_module.RegulatoryDomain.objects.create(code="GB", name="United Kingdom")
    band = efis_module.FrequencyBand.objects.create(
        regulatory_domain=domain,
        name="PMSE (EFIS)",
        start_frequency_mhz=470.0,
        end_frequency_mhz=790.0,
    )

    with pytest.raises(ValueError, match="applicationRanges"):
        EFISImportService._sync_region_application_bands(
            session=Mock(), domain=domain, region_id=1, region_name="Region", wireless_term_ids={1}
        )
    assert efis_module.FrequencyBand.objects.filter(pk=band.pk).exists()


@pytest.mark.django_db
def test_efis_import_keeps_manual_band_with_same_range(monkeypatch) -> None:
    monkeypatch.setattr(
        EFISImportService,
        "_request_json",
        Mock(
            return_value={
                "applicationRanges": [
                    {
                        "low": 470_000_000,
                        "high": 790_000_000,
                        "applications": [{"applicationTerm": {"id": 1, "name": "PMSE"}}],
                    }
                ]
            }
        ),
    )
    domain = efis_module.RegulatoryDomain.objects.create(code="GB", name="United Kingdom")
    manual = efis_module.FrequencyBand.objects.create(
        regulatory_domain=domain,
        name="Manual entry",
        band_type="restricted",
        start_frequency_mhz=470.0,
        end_frequency_mhz=790.0,
    )

    assert EFISImportService._sync_region_application_bands(
        session=Mock(), domain=domain, region_id=1, region_name="Region", wireless_term_ids={1}
    ) == (1, 0)
    manual.refresh_from_db()
    assert (manual.name, manual.band_type) == ("Manual entry", "restricted")
    assert domain.frequency_bands.filter(name__endswith="(EFIS)").count() == 1


def test_efis_request_decodes_gzip_body_once() -> None:
    body = gzip.compress(b'{"ok": true}')
    client, _ = _efis_client(
        httpx.Response(
            200,
            content=body,
            headers={"Content-Encoding": "gzip", "Content-Length": str(len(body))},
        )
    )
    assert EFISImportService._request_json(session=client, path="/test") == {"ok": True}
