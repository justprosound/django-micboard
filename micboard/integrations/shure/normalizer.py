"""Shure System API vocabulary for the shared device normalizer."""

from __future__ import annotations

from micboard.services.common.base.device_normalizer import VendorDeviceNormalizer

SHURE_NORMALIZER = VendorDeviceNormalizer(
    manufacturer_code="shure",
    family_aliases={
        "UHFR": "uhfr",
        "UHF_R": "uhfr",
        "QLXD": "qlxd",
        "QLX_D": "qlxd",
        "ULXD": "ulxd",
        "ULX_D": "ulxd",
        "AXIENT_DIGITAL": "axtd",
        "AXIENTDIGITAL": "axtd",
        "AXTD": "axtd",
        "AD": "axtd",
        "P10T": "p10t",
        "PSM1000": "p10t",
    },
    family_labels={
        "ulxd": "ULX-D",
        "qlxd": "QLX-D",
        "uhfr": "UHF-R",
        "axtd": "Axient Digital",
        "p10t": "P10T",
    },
)
