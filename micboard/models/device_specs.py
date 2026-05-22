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
            with open(fixture_file) as f:
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
        channels = spec.get("channels")
        if isinstance(channels, int):
            return channels
        try:
            return int(channels)  # type: ignore[arg-type]
        except Exception:
            return 4
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
        role = spec.get("role")
        if isinstance(role, str):
            return role
        return "receiver"
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
        dante = spec.get("dante")
        return bool(dante)
    return False
