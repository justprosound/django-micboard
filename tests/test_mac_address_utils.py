"""Unit coverage for MAC identity normalization helpers."""

from __future__ import annotations

from micboard.utils.mac_address import canonicalize_mac_address, mac_address_query_variants


def test_canonicalize_mac_address_rejects_unrelated_strings() -> None:
    """Invalid placeholders cannot become shared hardware identity keys."""
    assert canonicalize_mac_address("Device-AA-BB") is None
    assert canonicalize_mac_address(None) is None


def test_mac_address_query_variants_are_finite_and_complete() -> None:
    """Legacy lookup forms stay finite instead of expanding per-character case."""
    assert mac_address_query_variants("Aa-Bb-Cc-Dd-Ee-Ff") == {
        "aa:bb:cc:dd:ee:ff",
        "AA:BB:CC:DD:EE:FF",
        "aa-bb-cc-dd-ee-ff",
        "AA-BB-CC-DD-EE-FF",
        "aabbccddeeff",
        "AABBCCDDEEFF",
    }
    assert mac_address_query_variants("not-a-mac") == set()
