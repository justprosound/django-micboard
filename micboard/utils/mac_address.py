"""MAC-address identity normalization helpers."""

from __future__ import annotations

import re

_DELIMITED_MAC_ADDRESS_PATTERN = re.compile(r"[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}")
_COMPACT_MAC_ADDRESS_PATTERN = re.compile(r"[0-9A-Fa-f]{12}")


def canonicalize_mac_address(value: str | None) -> str | None:
    """Return a lowercase colon-delimited MAC or ``None`` for invalid input."""
    if value is None:
        return None

    candidate = value.strip()
    if _DELIMITED_MAC_ADDRESS_PATTERN.fullmatch(candidate) is not None:
        compact = candidate.replace("-", "").replace(":", "")
    elif _COMPACT_MAC_ADDRESS_PATTERN.fullmatch(candidate) is not None:
        compact = candidate
    else:
        return None
    compact = compact.lower()
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def mac_address_query_variants(value: str) -> frozenset[str]:
    """Return bounded exact-match variants for canonical and legacy MAC storage."""
    canonical = canonicalize_mac_address(value)
    if canonical is None:
        return frozenset()

    hyphenated = canonical.replace(":", "-")
    compact = canonical.replace(":", "")
    return frozenset(
        {
            canonical,
            canonical.upper(),
            hyphenated,
            hyphenated.upper(),
            compact,
            compact.upper(),
        }
    )
