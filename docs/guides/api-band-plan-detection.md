# API Band Plan Auto-Detection

## Overview

The WirelessChassis model now automatically detects band plan information from manufacturer APIs (Shure System API, etc.). This minimizes data entry by extracting `frequencyBand` from API responses and resolving it to standard band plans with min/max frequencies.

## How It Works

### 1. Shure System API provides `frequencyBand`

The Shure System API returns a `frequencyBand` field in device status responses:

```json
{
  "device_id": "ULXD4Q_001",
  "model": "ULXD4Q",
  "frequencyBand": "G50",
  "status": "online"
}
```

### 2. Detection Functions in device_specs.py

Three new functions handle band plan detection:

- **`detect_band_plan_from_api_string(api_band_value, manufacturer)`**
  - Input: API frequencyBand value (e.g., "G50", "G50 (470-534)")
  - Output: Normalized band plan name (e.g., "G50 (470-534 MHz)")
  - Handles multiple format variations from different manufacturers

- **`get_band_plan_from_model_code(manufacturer, model)`**
  - Input: Model code (e.g., "ULXD4Q", "AD4Q")
  - Output: Band plan name inferred from model
  - Fallback when API doesn't provide frequencyBand

- **`parse_band_plan_from_name(name)`**
  - Input: Band plan name with frequencies (e.g., "G50 (470-534 MHz)")
  - Output: Extracted min/max frequencies
  - Supports multiple format variations

### 3. WirelessChassis Services

#### Service: `detect_band_plan_from_api_data(chassis, api_band_value=None)`

Detects band plan from API frequency band value with preferred fallback to model code detection.

```python
from micboard.services.hardware.chassis_regulatory_service import detect_band_plan_from_api_data

chassis = WirelessChassis(manufacturer=shure, model="ULXD4Q")
result = detect_band_plan_from_api_data(chassis, api_band_value="G50")

# Returns a validated BandPlanInfo DTO:
result.name  # "G50"
result.min_mhz  # 470.0
result.max_mhz  # 534.0
result.source  # "api"
result.message  # "Detected from API frequencyBand 'G50'"
```

#### Service: `apply_detected_band_plan(chassis, api_band_value=None)`

Convenience method that applies detected band plan directly to the chassis:

```python
from micboard.services.hardware.chassis_regulatory_service import apply_detected_band_plan

chassis = WirelessChassis(manufacturer=shure, model="ULXD4Q")
if apply_detected_band_plan(chassis, api_band_value="G50"):
    chassis.save()
    # band_plan_name, band_plan_min_mhz, band_plan_max_mhz all set automatically
else:
    print("Could not detect band plan")
```

#### Automatic Detection on Save

When you set `band_plan_name` directly, `save()` automatically resolves frequencies:

```python
chassis = WirelessChassis(manufacturer=shure, model="ULXD4Q")
chassis.band_plan_name = "G50 (470-534 MHz)"
chassis.save()
# band_plan_min_mhz=470.0, band_plan_max_mhz=534.0 automatically populated
```

## Integration with Device Sync

### Using with Shure System API Sync

In your device sync code (e.g., `poll_devices` command or manufacturer plugin):

```python
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis

shure_mfg = Manufacturer.objects.get(code="shure")

# 1. Fetch device from Shure System API
api_response = shure_client.devices.get_device("ULXD4Q_001")

# 2. Create chassis with basic info
chassis, created = WirelessChassis.objects.update_or_create(
    manufacturer=shure_mfg,
    api_device_id=api_response["device_id"],
    defaults={
        "model": api_response["model"],
        "name": api_response.get("name", ""),
    }
)

# 3. Auto-detect band plan from API frequencyBand
from micboard.services.hardware.chassis_regulatory_service import apply_detected_band_plan

apply_detected_band_plan(chassis, api_band_value=api_response.get("frequencyBand"))
chassis.save()

print(f"✅ Setup band plan: {chassis.band_plan_name}")
# Output: ✅ Setup band plan: G50 (470-534 MHz)
```

### Bulk Update from API

```python
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.chassis_regulatory_service import apply_detected_band_plan

# Update all online Shure devices
for chassis in WirelessChassis.objects.filter(
    manufacturer__code="shure",
    status="online"
):
    # Get current status from API
    api_status = shure_client.devices.get_device(chassis.api_device_id)

    # Apply detected band plan
    if apply_detected_band_plan(
        chassis,
        api_band_value=api_status.get("frequencyBand")
    ):
        chassis.save(update_fields=["band_plan_name", "band_plan_min_mhz", "band_plan_max_mhz"])
        print(f"✅ {chassis.name}: {chassis.band_plan_name}")
    else:
        print(f"⚠️  {chassis.name}: Could not detect band plan")
```

## Supported API Format Variations

The detector handles multiple format variations from different manufacturers:

| API Value | Detected As | Source |
|-----------|------------|--------|
| `G50` | `G50 (470-534 MHz)` | Registry lookup |
| `G50 (470-534)` | `G50 (470-534 MHz)` | Registry lookup |
| `G50 (470-534 MHz)` | `G50 (470-534 MHz)` | Registry lookup |
| `470-534` | `G50 (470-534 MHz)` | Registry lookup by frequency range |
| (missing) | `G50 (470-534 MHz)` | Model code inference (ULXD4Q → G50) |

## API frequencyBand Values by Manufacturer

### Shure Wireless Systems

| Model | Typical frequencyBand | Band Plan |
|-------|----------------------|-----------|
| ULXD4Q | `G50` | G50 (470-534 MHz) |
| ULXD4D | `G50` | G50 (470-534 MHz) |
| AD4Q | `G50` | G50 (470-534 MHz) |
| ULXD1 (handheld) | `G50` | G50 (470-534 MHz) |
| ULXD2/ULXD4 (older) | Variable | Check API response |
| Axient Digital ANX4 | `G50` | G50 (470-534 MHz) |

Note: As of 25.01.26, actual API responses from https://localhost:10000/v1.0/devices should be tested to confirm `frequencyBand` field availability and format.

### Sennheiser Wireless Systems

Currently developing Sennheiser support. Expected format similar to Shure.

## Fallback Strategy

If API doesn't provide `frequencyBand`, the detector falls back to model code inference:

1. **API Detection** (preferred)
   - Uses `frequencyBand` from API
   - Most accurate, manufacturer-provided

2. **Model Code Detection** (fallback)
   - Infers from model number (e.g., ULXD4Q → G50)
   - Useful when API doesn't provide frequencyBand
   - Uses pattern matching in `get_band_plan_from_model_code()`

3. **Manual Entry** (last resort)
   - Admin selects from dropdown
   - Frequencies auto-populate

## Testing Queries

### Check Available Band Plans

```python
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.band_plans import get_available_band_plans
from micboard.models.hardware.wireless_chassis import WirelessChassis

shure = Manufacturer.objects.get(code="shure")
chassis = WirelessChassis(manufacturer=shure)

plans = get_available_band_plans(manufacturer=chassis.manufacturer.code)
# Output: [
#   ("g50_470_534", "G50 (470-534 MHz)"),
#   ("h50_520_600", "H50 (520-600 MHz)"),
#   ...
# ]
```

### Test Detection

```python
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.chassis_regulatory_service import (
    apply_detected_band_plan,
    detect_band_plan_from_api_data,
)

chassis = WirelessChassis(manufacturer=shure, model="ULXD4Q")

# Test API detection
result = detect_band_plan_from_api_data(chassis, api_band_value="G50")
print(result.name)  # "G50"

# Test model detection (no API value)
result = detect_band_plan_from_api_data(chassis, api_band_value=None)
print(result.name)  # "G50" (from ULXD4Q model code)

# Test apply
if apply_detected_band_plan(chassis, api_band_value="G50"):
    print(f"{chassis.band_plan_min_mhz}-{chassis.band_plan_max_mhz} MHz")
    # Output: 470.0-534.0 MHz
```

## Data Accuracy

- **Registry accuracy**: Band plans sourced from official manufacturer specifications
- **Model inference**: ULXD models map to G50, H50, etc. based on model code patterns
- **Frequency ranges**: Min/max frequencies verified against regulatory and manufacturer documentation
- **Fallback behavior**: If API omits frequencyBand, model code inference provides reasonable defaults

## Continuing Development

As API integrations mature, this system can be extended to:
- Store API response history for debugging
- Track band plan changes over time
- Validate band plan against regulatory domains
- Alert on mismatches between API and stored data
