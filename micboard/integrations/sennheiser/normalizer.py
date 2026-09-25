"""Sennheiser SSCv2 vocabulary for the shared device normalizer."""

from __future__ import annotations

from micboard.services.common.base.device_normalizer import VendorDeviceNormalizer

SENNHEISER_NORMALIZER = VendorDeviceNormalizer(
    manufacturer_code="sennheiser",
    family_aliases={
        "EVOLUTION_WIRELESS_DIGITAL": "ewd",
        "EW_D": "ewd",
        "TEAMCONNECT": "teamconnect",
        "TEAM_CONNECT": "teamconnect",
    },
    family_labels={
        "ewd": "Evolution Wireless Digital",
        "teamconnect": "TeamConnect",
    },
)
