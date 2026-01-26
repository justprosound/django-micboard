"""Compliance service for RF frequency validation and regulatory checks.

Handles:
- Frequency allow/block list checking
- Geo-fencing compliance
- Licensing requirements
"""

from __future__ import annotations

import logging
from typing import TypedDict

from micboard.models import (
    ActivityLog,
    Building,
    ExclusionZone,
    FrequencyBand,
    RegulatoryDomain,
)

logger = logging.getLogger(__name__)


class ComplianceResult(TypedDict):
    """Compliance check result details used by ComplianceService methods."""

    is_compliant: bool
    status: str  # 'allowed', 'restricted', 'forbidden', 'excluded', 'unknown'
    reason: str
    requires_license: bool
    power_limit_mw: int | None
    licensing_info: str
    fee_structure: str
    advisory_notice: str


class ComplianceService:
    """Service for checking RF compliance against regulatory domains and exclusion zones."""

    DISCLAIMER_TEXT = (
        "IMPORTANT: This information is advisory only and does not constitute legal advice. "
        "Licensing terms, fees, and regulatory status are subject to change by "
        "national authorities. "
        "Users are responsible for verifying compliance with local laws and "
        "obtaining necessary licenses "
        "from the relevant regulatory body. For more information, visit "
        '<a href="https://apwpt.org/" title="APWPT - Association for securing radio '
        'spectrum for the cultural and creative industries">APWPT</a> '
        'and consult the <a href="https://apwpt.org/wp-content/uploads/2025/09/'
        'Handout_Version-2025_September.pdf" title="APWPT Handout Version '
        'September 2025">September 2025 Handout</a>.'
    )

    @classmethod
    def check_frequency(
        cls,
        frequency_mhz: float,
        building: Building | None = None,
        regulatory_domain: RegulatoryDomain | None = None,
    ) -> ComplianceResult:
        """Check if a frequency is compliant in a specific context.

        Args:
            frequency_mhz: Frequency to check in MHz
            building: Building context (to determine regulatory domain and exclusion zones)
            regulatory_domain: Specific domain override (if building not provided)

        Returns:
            ComplianceResult dict
        """
        # Determine applicable regulatory domain
        domain = regulatory_domain
        if not domain and building and building.regulatory_domain:
            domain = building.regulatory_domain

        # If no domain found, we can't check compliance authoritatively
        if not domain:
            return {
                "is_compliant": True,  # Assume compliant if no rules exist (soft fail)
                "status": "unknown",
                "reason": "No regulatory domain defined",
                "requires_license": False,
                "power_limit_mw": None,
                "licensing_info": "",
                "fee_structure": "",
                "advisory_notice": cls.DISCLAIMER_TEXT,
            }

        # Check Global Domain Bounds
        if frequency_mhz < domain.min_frequency_mhz or frequency_mhz > domain.max_frequency_mhz:
            pass

        # 1. Check Exclusion Zones
        exclusion_zones = ExclusionZone.objects.filter(
            regulatory_domain=domain,
            is_active=True,
            start_frequency_mhz__lte=frequency_mhz,
            end_frequency_mhz__gte=frequency_mhz,
        )

        if exclusion_zones.exists():
            zone = exclusion_zones.first()
            return {
                "is_compliant": False,
                "status": "excluded",
                "reason": f"Inside exclusion zone: {zone.name} ({zone.reason})",
                "requires_license": False,
                "power_limit_mw": 0,
                "licensing_info": "",
                "fee_structure": "",
                "advisory_notice": cls.DISCLAIMER_TEXT,
            }

        # 2. Check Frequency Bands
        band = FrequencyBand.objects.filter(
            regulatory_domain=domain,
            start_frequency_mhz__lte=frequency_mhz,
            end_frequency_mhz__gte=frequency_mhz,
        ).first()

        if not band:
            return {
                "is_compliant": False,
                "status": "unknown",
                "reason": "Frequency not defined in any band for this domain",
                "requires_license": False,
                "power_limit_mw": None,
                "licensing_info": "",
                "fee_structure": "",
                "advisory_notice": cls.DISCLAIMER_TEXT,
            }

        if band.band_type == "forbidden":
            return {
                "is_compliant": False,
                "status": "forbidden",
                "reason": f"Forbidden band: {band.name}",
                "requires_license": False,
                "power_limit_mw": 0,
                "licensing_info": band.licensing_info,
                "fee_structure": band.fee_structure,
                "advisory_notice": cls.DISCLAIMER_TEXT,
            }

        if band.band_type == "guard":
            return {
                "is_compliant": False,
                "status": "forbidden",
                "reason": f"Guard band: {band.name}",
                "requires_license": False,
                "power_limit_mw": 0,
                "licensing_info": band.licensing_info,
                "fee_structure": band.fee_structure,
                "advisory_notice": cls.DISCLAIMER_TEXT,
            }

        if band.band_type == "restricted":
            return {
                "is_compliant": True,
                "status": "restricted",
                "reason": f"Restricted band: {band.name}",
                "requires_license": True,
                "power_limit_mw": band.power_limit_mw,
                "licensing_info": band.licensing_info,
                "fee_structure": band.fee_structure,
                "advisory_notice": cls.DISCLAIMER_TEXT,
            }

        # Allowed
        return {
            "is_compliant": True,
            "status": "allowed",
            "reason": f"Allowed band: {band.name}",
            "requires_license": False,
            "power_limit_mw": band.power_limit_mw,
            "licensing_info": band.licensing_info,
            "fee_structure": band.fee_structure,
            "advisory_notice": cls.DISCLAIMER_TEXT,
        }

    @classmethod
    def audit_compliance_check(
        cls, frequency_mhz: float, result: ComplianceResult, user=None, context: str = ""
    ):
        """Log a failed compliance check."""
        if not result["is_compliant"] or result["status"] == "restricted":
            ActivityLog.objects.create(
                activity_type=ActivityLog.ACTIVITY_COMPLIANCE,
                operation="check",
                user=user,
                summary=f"Compliance check {result['status']}: {frequency_mhz} MHz",
                details={
                    "frequency": frequency_mhz,
                    "result": result,
                    "context": context,
                },
                status="warning" if result["is_compliant"] else "failed",
            )
