"""Service for importing EFIS (ECO Frequency Information System) data.

Fetches live regulatory application ranges from the official CEPT EFIS API
(`https://efisapi.cept.org/v2/api-docs`) and maps wireless-audio focused
applications (PMSE / radio microphones / ALD) into `FrequencyBand` records.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import timedelta

from django.utils import timezone

import requests
from requests import RequestException

from micboard.integrations.base_http_client import create_resilient_session
from micboard.models import (
    ActivityLog,
    FrequencyBand,
    RegulatoryDomain,
)

logger = logging.getLogger(__name__)


class EFISImportService:
    """Service to handle EFIS data imports."""

    # EFIS API Base URL (docs: https://efisapi.cept.org/v2/api-docs)
    EFIS_URL = "https://efisapi.cept.org"
    REQUEST_TIMEOUT_SECONDS = 20
    _WIRELESS_KEYWORDS: Sequence[str] = ("micro", "pmse", "ald")
    _EXCLUDED_REGION_CODES: set[str] = {"ECA", "ITU"}

    @classmethod
    def get_last_import_date(cls):
        """Get the date of the last successful EFIS import."""
        last_log = (
            ActivityLog.objects.filter(
                activity_type=ActivityLog.ACTIVITY_COMPLIANCE,
                operation="import",
                status="success",
                summary__contains="EFIS",
            )
            .order_by("-created_at")
            .first()
        )

        return last_log.created_at if last_log else None

    @classmethod
    def is_outdated(cls, days_threshold: int = 30) -> bool:
        """Check if the EFIS data is outdated (older than threshold)."""
        last_date = cls.get_last_import_date()
        if not last_date:
            return True

        cutoff = timezone.now() - timedelta(days=days_threshold)
        return last_date < cutoff

    @classmethod
    def run_import(cls, user=None) -> dict:
        """Execute the import process against the official EFIS API.

        The importer pulls region metadata, identifies wireless-audio application terms
        (PMSE/Radio microphones/ALD), and writes `FrequencyBand` rows per application
        range using MHz units. Bands are upserted to avoid duplicates on repeated runs.
        """
        ActivityLog.objects.create(
            activity_type=ActivityLog.ACTIVITY_COMPLIANCE,
            operation="start",
            user=user,
            summary="Started EFIS regulatory import (API)",
            status="success",
        )

        session = create_resilient_session(max_retries=3, backoff_factor=0.5)
        session.headers.update({"Accept": "application/json"})

        domains_updated = 0
        bands_created = 0
        bands_updated = 0

        try:
            wireless_term_ids = cls._fetch_wireless_term_ids(session)
            regions = cls._fetch_regions(session)

            for region in regions:
                if region.get("regionCode") in cls._EXCLUDED_REGION_CODES:
                    continue

                domain, _ = RegulatoryDomain.objects.update_or_create(
                    code=region.get("regionCode", "").upper(),
                    defaults={
                        "name": region.get("name", "Unknown Region"),
                        "description": "Imported from CEPT EFIS applications API",
                        "country_code": cls._normalize_country_code(region.get("regionCode", "")),
                    },
                )

                created, updated = cls._sync_region_application_bands(
                    session=session,
                    domain=domain,
                    region_id=region.get("id"),
                    region_name=region.get("name", ""),
                    wireless_term_ids=wireless_term_ids,
                )

                domains_updated += 1
                bands_created += created
                bands_updated += updated

            ActivityLog.objects.create(
                activity_type=ActivityLog.ACTIVITY_COMPLIANCE,
                operation="import",
                user=user,
                summary="Successfully imported EFIS regulatory data (API)",
                details={
                    "source": cls.EFIS_URL,
                    "domains_updated": domains_updated,
                    "bands_created": bands_created,
                    "bands_updated": bands_updated,
                },
                status="success",
            )

            return {
                "success": True,
                "message": "Import completed successfully",
                "domains_updated": domains_updated,
                "bands_created": bands_created,
                "bands_updated": bands_updated,
            }

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("EFIS import failed")
            ActivityLog.objects.create(
                activity_type=ActivityLog.ACTIVITY_COMPLIANCE,
                operation="failure",
                user=user,
                summary=f"EFIS import failed: {exc}",
                status="failed",
                error_message=str(exc),
            )
            return {"success": False, "message": str(exc)}
        finally:
            session.close()

    @classmethod
    def _fetch_regions(cls, session: requests.Session) -> list[dict]:
        payload = cls._request_json(session=session, path="/regions/all")
        return payload.get("regions", [])

    @classmethod
    def _fetch_wireless_term_ids(cls, session: requests.Session) -> set[int]:
        payload = cls._request_json(session=session, path="/applications/terms")
        term_ids: set[int] = set()
        for term in payload.get("terms", []):
            name = term.get("name", "").lower()
            if any(keyword in name for keyword in cls._WIRELESS_KEYWORDS):
                term_id = term.get("id")
                if isinstance(term_id, int):
                    term_ids.add(term_id)
        if not term_ids:
            raise ValueError("EFIS term discovery returned no wireless-related terms")
        return term_ids

    @classmethod
    def _sync_region_application_bands(
        cls,
        *,
        session: requests.Session,
        domain: RegulatoryDomain,
        region_id: int,
        region_name: str,
        wireless_term_ids: set[int],
    ) -> tuple[int, int]:
        payload = cls._request_json(
            session=session,
            path="/applications/ranges",
            params={"regionId": region_id},
        )

        created = 0
        updated = 0

        for app_range in payload.get("applicationRanges", []):
            applications: Sequence[dict] = app_range.get("applications", [])
            matching = [
                app
                for app in applications
                if cls._matches_wireless_application(app, wireless_term_ids)
            ]
            if not matching:
                continue

            start_mhz = cls._hz_to_mhz(app_range.get("low", 0))
            end_mhz = cls._hz_to_mhz(app_range.get("high", 0))
            band_name = cls._build_band_name(matching)
            description = cls._build_description(region_name=region_name, applications=matching)

            _, was_created = FrequencyBand.objects.update_or_create(
                regulatory_domain=domain,
                start_frequency_mhz=start_mhz,
                end_frequency_mhz=end_mhz,
                defaults={
                    "name": band_name,
                    "band_type": "allowed",
                    "description": description,
                    "licensing_info": cls._combine_comments(matching),
                },
            )

            if was_created:
                created += 1
            else:
                updated += 1

        return created, updated

    @classmethod
    def _request_json(
        cls,
        *,
        session: requests.Session,
        path: str,
        params: dict | None = None,
    ) -> dict:
        url = f"{cls.EFIS_URL}{path}"
        try:
            response = session.get(url, params=params, timeout=cls.REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except RequestException as exc:  # pragma: no cover - network failures
            raise RuntimeError(f"EFIS request failed for {url}: {exc}") from exc

    @classmethod
    def _matches_wireless_application(cls, application: dict, wireless_term_ids: set[int]) -> bool:
        term = application.get("applicationTerm", {})
        term_id = term.get("id")
        term_name = (term.get("name") or "").lower()
        if term_id in wireless_term_ids:
            return True
        return any(keyword in term_name for keyword in cls._WIRELESS_KEYWORDS)

    @classmethod
    def _build_band_name(cls, applications: Sequence[dict]) -> str:
        names = sorted(
            {app.get("applicationTerm", {}).get("name", "Wireless audio") for app in applications}
        )
        base = ", ".join(names) if names else "Wireless audio"
        return f"{base} (EFIS)"

    @classmethod
    def _build_description(cls, *, region_name: str, applications: Sequence[dict]) -> str:
        comments = cls._combine_comments(applications)
        if comments:
            return f"EFIS application range for {region_name}. Comments: {comments}"
        return f"EFIS application range for {region_name}."

    @classmethod
    def _combine_comments(cls, applications: Sequence[dict]) -> str:
        comments: list[str] = []
        for app in applications:
            comment = (app.get("comment") or "").strip()
            if comment:
                comments.append(comment)
        return "; ".join(dict.fromkeys(comments))

    @classmethod
    def _hz_to_mhz(cls, hz_value: float | int) -> float:
        return round(float(hz_value) / 1_000_000.0, 6)

    @classmethod
    def _normalize_country_code(cls, region_code: str) -> str:
        if not region_code:
            return ""
        cleaned = region_code.strip().upper()
        if len(cleaned) == 2:
            return cleaned
        return ""
