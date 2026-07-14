"""Prevent deprecated model-to-service delegation APIs from returning."""

from __future__ import annotations

import micboard.services.hardware as hardware_services
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.rf_coordination.rf_channel import RFChannel


def test_rf_channel_service_shims_are_absent() -> None:
    removed = (
        "is_receive_channel",
        "is_send_channel",
        "get_regulatory_domain",
        "has_regulatory_coverage",
        "needs_regulatory_update",
        "get_regulatory_status",
    )
    for name in removed:
        assert not hasattr(RFChannel, name)


def test_wireless_chassis_service_shims_are_absent() -> None:
    removed = (
        "is_active_at_time",
        "get_regulatory_domain",
        "has_band_plan",
        "get_available_band_plans",
        "detect_band_plan_from_api_data",
        "apply_detected_band_plan",
        "has_band_plan_regulatory_coverage",
        "needs_band_plan_regulatory_update",
        "get_band_plan_regulatory_status",
    )
    for name in removed:
        assert not hasattr(WirelessChassis, name)


def test_hardware_service_package_has_no_reexports() -> None:
    removed = (
        "apply_detected_band_plan",
        "detect_band_plan_from_api_data",
        "get_available_band_plans",
        "get_band_plan_status",
        "get_gap_analysis_context",
        "get_gap_analysis_summary",
        "is_active_at_time",
        "prepare_chassis_for_save",
    )
    for name in removed:
        assert not hasattr(hardware_services, name)
