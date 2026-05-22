"""Band plan specifications: frequency ranges and regional allocations.

Loads band plan specifications from fixtures/band_plans.yaml.
Each band plan defines a frequency range, region, and name for wireless
microphone systems.
"""

from __future__ import annotations

import importlib.resources
import logging
from typing import Any

# Ensure 'yaml' is typed as optional module to satisfy static type checkers
yaml: Any = None
try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover - optional dependency
    yaml = None
    HAS_YAML = False


logger = logging.getLogger(__name__)


# Load band plan specifications from fixture
def _load_band_plans() -> dict[str, dict[str, dict]]:
    """Load band plan specifications from YAML fixture."""
    if not HAS_YAML:
        logger.warning("PyYAML not installed; band plan specifications are unavailable")
        return {}

    try:
        # Try Python 3.9+ importlib.resources
        if hasattr(importlib.resources, "files"):
            fixture_path = importlib.resources.files("micboard").joinpath(
                "fixtures/band_plans.yaml"
            )
            spec_yaml = fixture_path.read_text()
        else:
            # Fallback for older Python versions
            import os

            fixture_file = os.path.join(
                os.path.dirname(__file__), "..", "fixtures", "band_plans.yaml"
            )
            with open(fixture_file) as f:
                spec_yaml = f.read()

        return yaml.safe_load(spec_yaml) or {}
    except Exception:
        # If band plans fixture doesn't exist, return empty dict (non-critical)
        logger.exception("Failed to load band plan specifications")
        return {}


# Band plan specifications by manufacturer
BAND_PLAN_SPECIFICATIONS: dict[str, dict[str, dict]] = _load_band_plans()


def get_band_plan(*, manufacturer: str | None, band_plan_key: str | None) -> dict | None:
    """Look up band plan specifications by manufacturer and band plan key.

    Args:
        manufacturer: Manufacturer code (e.g., "shure", "sennheiser")
        band_plan_key: Band plan identifier (e.g., "g50", "aw_plus")

    Returns:
        Band plan dict with keys: name, min_mhz, max_mhz, region
        None if not found
    """
    if not manufacturer or not band_plan_key:
        return None

    mfg_lower = manufacturer.lower()
    if mfg_lower not in BAND_PLAN_SPECIFICATIONS:
        return None

    band_key_lower = band_plan_key.lower().replace(" ", "_").replace("-", "_")
    return BAND_PLAN_SPECIFICATIONS[mfg_lower].get(band_key_lower)


def get_available_band_plans(*, manufacturer: str | None) -> list[tuple[str, str]]:
    """Get list of available band plans for a manufacturer.

    Args:
        manufacturer: Manufacturer code (e.g., "shure", "sennheiser")

    Returns:
        List of (key, name) tuples for all available band plans
        Empty list if manufacturer not found
    """
    if not manufacturer:
        return []

    mfg_lower = manufacturer.lower()
    if mfg_lower not in BAND_PLAN_SPECIFICATIONS:
        return []

    return [(key, plan["name"]) for key, plan in BAND_PLAN_SPECIFICATIONS[mfg_lower].items()]


def parse_band_plan_from_name(*, name: str) -> dict | None:
    """Parse frequency range from a band plan name string.

    Attempts to extract min/max frequencies from common name patterns like:
    - "G50 (470-534 MHz)"
    - "Aw+ (470-558 MHz)"
    - "Block 470 (470-537 MHz)"

    Args:
        name: Band plan name string

    Returns:
        Dict with 'min_mhz' and 'max_mhz' if parsing successful
        None if unable to parse
    """
    import re

    # Match pattern like "470-534 MHz" or "470-534MHz"
    match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*MHz", name, re.IGNORECASE)
    if match:
        return {
            "min_mhz": float(match.group(1)),
            "max_mhz": float(match.group(2)),
        }

    return None


def _normalize_band_key(val: str) -> str:
    return val.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")


def _extract_band_code(val: str) -> str | None:
    import re

    m = re.match(r"^([a-zA-Z0-9]+)", val)
    return m.group(1).lower() if m else None


def _extract_freq_range(val: str) -> tuple[float, float] | None:
    import re

    m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", val)
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except (ValueError, TypeError):
        return None


def detect_band_plan_from_api_string(
    *, api_band_value: str | None, manufacturer: str | None = "shure"
) -> str | None:
    """Detect and return band plan name from API frequencyBand string.

    Uses module-level helpers to keep this function concise and easier to
    maintain; strategies include exact key match, code-prefix match, exact
    frequency-range match, and partial string match.
    """
    if not api_band_value:
        return None

    api_band_value = str(api_band_value).strip()
    if not api_band_value:
        return None

    mfg = (manufacturer or "shure").lower()
    band_plans = BAND_PLAN_SPECIFICATIONS.get(mfg, {})

    # Strategy 1: Exact registry key
    key = _normalize_band_key(api_band_value)
    plan = band_plans.get(key)
    if plan:
        return plan.get("name")

    # Strategy 2: Match by leading code (e.g., "G50")
    code = _extract_band_code(api_band_value)
    if code:
        for registry_key, plan_data in band_plans.items():
            if registry_key.startswith(code):
                return plan_data.get("name")

    # Strategy 3: Exact frequency range match
    freq = _extract_freq_range(api_band_value)
    if freq:
        api_min, api_max = freq
        for plan_data in band_plans.values():
            plan_min = plan_data.get("min_mhz") or 0
            plan_max = plan_data.get("max_mhz") or 0
            if plan_min == api_min and plan_max == api_max:
                return plan_data.get("name")

    # Strategy 4: Partial string matching as a fallback
    api_normalized = api_band_value.lower().replace(" ", "_").replace("-", "_")
    for registry_key, plan_data in band_plans.items():
        if api_normalized in registry_key or registry_key in api_normalized:
            return plan_data.get("name")

    return None


def get_band_plan_from_model_code(*, manufacturer: str | None, model: str | None) -> str | None:
    """Get default band plan for a device model based on manufacturer specs.

    Some device models have a default/standard band plan. For example:
    - Shure ULX-D G5 variant is typically G50 band
    - Sennheiser ew 100 G3 might be A band

    Args:
        manufacturer: Manufacturer code
        model: Device model string

    Returns:
        Band plan name if model has a standard band plan, None otherwise
    """
    if not manufacturer or not model:
        return None

    # Parse model for band hints
    # e.g., "ULXD4Q-G50" → G50
    # e.g., "EM 6062-G3 (-E)" → G band (not specific enough)
    import re

    # Try to extract band code from model string
    # Patterns like "G50", "G5", "Aw+" etc.
    band_patterns = [
        r"[_-]?([GHJKLBCABw]+\d+(?:\+)?)",  # G50, J7, Aw+, etc.
        r"^([GHJKLBCABw]+\d+(?:\+)?)",  # At start of model
    ]

    for pattern in band_patterns:
        match = re.search(pattern, model, re.IGNORECASE)
        if match:
            band_code = match.group(1).lower()
            # Try to find this in band plans
            band_plan = detect_band_plan_from_api_string(
                api_band_value=band_code, manufacturer=manufacturer
            )
            if band_plan:
                return band_plan

    return None
