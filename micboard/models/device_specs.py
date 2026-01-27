"""Device specifications: channel capabilities, roles, and features.

Loads specifications for wireless audio devices from fixtures/device_specifications.yaml.
Each device is characterized by:
  - Role: receiver (receives from field), transmitter (sends to field), or transceiver (both)
  - Channels: number of RF channels
  - Dante: whether it supports Dante audio networking
  - Bodypack capability: what types of field devices it can work with

Supported Manufacturers: Shure, Sennheiser, Wisycom, ULBACO, etc.
"""

from __future__ import annotations

import importlib.resources
import logging

try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover - optional dependency
    yaml = None
    HAS_YAML = False


logger = logging.getLogger(__name__)


# Load device specifications from fixture
def _load_device_specifications() -> dict[str, dict[str, dict]]:
    """Load device specifications from YAML fixture."""
    if not HAS_YAML:
        logger.warning("PyYAML not installed; device specifications are unavailable")
        return {}

    try:
        # Try Python 3.9+ importlib.resources
        if hasattr(importlib.resources, "files"):
            fixture_path = importlib.resources.files("micboard").joinpath(
                "fixtures/device_specifications.yaml"
            )
            spec_yaml = fixture_path.read_text()
        else:
            # Fallback for older Python versions
            import os

            fixture_file = os.path.join(
                os.path.dirname(__file__), "..", "fixtures", "device_specifications.yaml"
            )
            with open(fixture_file, "r") as f:
                spec_yaml = f.read()

        return yaml.safe_load(spec_yaml) or {}
    except Exception:
        logger.exception("Failed to load device specifications fixture")
        return {}


# Unified device specifications by manufacturer
DEVICE_SPECIFICATIONS: dict[str, dict[str, dict]] = _load_device_specifications()

if not DEVICE_SPECIFICATIONS:
    logger.warning("Device specifications fixture is empty or unavailable")


def get_device_spec(*, manufacturer: str | None, model: str | None) -> dict | None:
    """Look up device specifications by manufacturer and model.

    Args:
        manufacturer: Manufacturer code (e.g., "shure", "sennheiser", "wisycom")
        model: Device model string (e.g., "AD4Q", "Spectera Base")

    Returns:
        Spec dict with keys: channels, role, dante, name, models
        None if not found
    """
    if not manufacturer or not model:
        return None

    mfg_lower = manufacturer.lower()
    if mfg_lower not in DEVICE_SPECIFICATIONS:
        return None

    mfg_specs = DEVICE_SPECIFICATIONS[mfg_lower]
    model_upper = model.upper().replace("-", "").replace(" ", "")

    # Search all specs under this manufacturer
    for _spec_key, spec_data in mfg_specs.items():
        for model_variant in spec_data.get("models", []):
            if model_variant.upper().replace("-", "").replace(" ", "") == model_upper:
                return spec_data

    return None


def get_channel_count(*, manufacturer: str | None, model: str | None) -> int:
    """Get channel count for a device.

    Args:
        manufacturer: Manufacturer code (e.g., "shure", "sennheiser")
        model: Device model string

    Returns:
        Number of channels (defaults to 4 if unknown)
    """
    spec = get_device_spec(manufacturer=manufacturer, model=model)
    if spec:
        return spec.get("channels", 4)
    return 4  # Conservative default


def get_device_role(*, manufacturer: str | None, model: str | None) -> str:
    """Get device role/type.

    Args:
        manufacturer: Manufacturer code
        model: Device model string

    Returns:
        Role: "receiver", "transmitter", or "transceiver"
        Defaults to "receiver" if unknown
    """
    spec = get_device_spec(manufacturer=manufacturer, model=model)
    if spec:
        return spec.get("role", "receiver")
    return "receiver"  # Conservative default


def get_dante_support(*, manufacturer: str | None, model: str | None) -> bool:
    """Check if device supports Dante audio networking.

    Args:
        manufacturer: Manufacturer code
        model: Device model string

    Returns:
        True if device has Dante support
    """
    spec = get_device_spec(manufacturer=manufacturer, model=model)
    if spec:
        return spec.get("dante", False)
    return False


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
            with open(fixture_file, "r") as f:
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


def detect_band_plan_from_api_string(
    *, api_band_value: str | None, manufacturer: str | None = "shure"
) -> str | None:
    """Detect and return band plan name from Shure/Sennheiser API frequencyBand string.

    The Shure System API returns frequencyBand in various formats:
    - "G50" → "G50 (470-534 MHz)"
    - "G50 (470-534)" → "G50 (470-534 MHz)"
    - "470-534" → tries to match to a band plan, falls back to parsing
    - "UHF Band IV" → matches to registry

    Args:
        api_band_value: Raw frequencyBand string from API (e.g., "G50", "G50 (470-534)")
        manufacturer: Manufacturer code (default: "shure")

    Returns:
        Full band plan name string (e.g., "G50 (470-534 MHz)"), or None if no match
    """
    if not api_band_value:
        return None

    api_band_value = str(api_band_value).strip()
    if not api_band_value:
        return None

    if not manufacturer:
        manufacturer = "shure"

    mfg_lower = manufacturer.lower()
    band_plans = BAND_PLAN_SPECIFICATIONS.get(mfg_lower, {})

    # Strategy 1: Try exact key match (case-insensitive)
    # e.g., "g50" → "G50 (470-534 MHz)"
    band_key = (
        api_band_value.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
    )
    for registry_key, plan_data in band_plans.items():
        if registry_key == band_key:
            return plan_data.get("name")

    # Strategy 2: Try to match by extracting the code part
    # e.g., "G50 (470-534)" → extract "G50" and match
    import re

    code_match = re.match(r"^([a-zA-Z0-9]+)", api_band_value)
    if code_match:
        code = code_match.group(1).lower()
        for registry_key, plan_data in band_plans.items():
            if registry_key.startswith(code):
                return plan_data.get("name")

    # Strategy 3: Try to match by frequency range
    # e.g., "470-534" → find band with matching range
    freq_match = re.search(r"(\d+)-(\d+)", api_band_value)
    if freq_match:
        try:
            api_min = float(freq_match.group(1))
            api_max = float(freq_match.group(2))
            for plan_data in band_plans.values():
                plan_min = plan_data.get("min_mhz", 0)
                plan_max = plan_data.get("max_mhz", 0)
                if plan_min == api_min and plan_max == api_max:
                    return plan_data.get("name")
        except (ValueError, TypeError):
            pass

    # Strategy 4: Try partial string match
    # e.g., "Band IV" might match "band_iv"
    api_normalized = api_band_value.lower().replace(" ", "_").replace("-", "_")
    for registry_key, plan_data in band_plans.items():
        if api_normalized in registry_key or registry_key in api_normalized:
            return plan_data.get("name")

    # No match found
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
