# Band Plan Auto-Population Guide

## Overview

When configuring wireless chassis devices in Django Micboard, you can select from **standard band plans** to automatically populate frequency ranges. This eliminates the need to manually enter `band_plan_min_mhz` and `band_plan_max_mhz` values for each device.

## How It Works

### 1. Automatic Frequency Population

When you save a WirelessChassis with a `band_plan_name` set, the system:

1. **Looks up the band plan** in the registry (`micboard/fixtures/band_plans.yaml`)
2. **Auto-populates** `band_plan_min_mhz` and `band_plan_max_mhz` fields
3. **No manual entry needed** for standard manufacturer band plans

### 2. Three Ways to Set Band Plans

#### Option A: Admin Dropdown (Recommended)
1. Open WirelessChassis in Django admin
2. Ensure **Manufacturer** is set (required for band plan lookup)
3. In "Band Plan Configuration" section, use **"Select Standard Band Plan"** dropdown
4. Select a band plan (e.g., "G50 (470-534 MHz)")
5. Save → frequencies auto-populate

#### Option B: Direct Name Entry with Parsing
Enter a band plan name that includes frequency range in format:
- `"G50 (470-534 MHz)"` → parses to 470-534 MHz
- `"Aw+ (470-558 MHz)"` → parses to 470-558 MHz
- `"Block 470 (470-537 MHz)"` → parses to 470-537 MHz

The system uses regex to extract frequencies from the name.

#### Option C: Manual Entry
Set all three fields manually:
- `band_plan_name`: Custom name (e.g., "Custom UHF Range")
- `band_plan_min_mhz`: 470.0
- `band_plan_max_mhz`: 534.0

## Supported Band Plans

### Shure
- **G50** (470-534 MHz) - US/EU
- **H50** (534-598 MHz) - US/EU
- **J50** (572-636 MHz) - US
- **L50** (632-696 MHz) - US
- **J7** (578-608 MHz) - US
- **K54** (596-632 MHz) - US/EU
- **L3** (638-698 MHz) - US
- **H19** (506-542 MHz) - EU
- **J8** (520-586 MHz) - EU

### Sennheiser
- **Aw+** (470-558 MHz) - EU
- **Bw** (626-698 MHz) - US
- **A1-5** (470-516 MHz) - EU
- **A6-10** (516-558 MHz) - EU
- **B1-5** (614-638 MHz) - US
- **B6-10** (638-662 MHz) - US
- **C1-5** (734-758 MHz) - US
- **C6-10** (758-782 MHz) - US
- **EW Range** (470-550 MHz) - EU

### Lectrosonics
- **Block 470** (470-537 MHz) - US/EU
- **Block 19** (486-608 MHz) - US
- **Block 21** (537-614 MHz) - US/EU
- **Block 22** (614-691 MHz) - US
- **Block 24** (537-691 MHz) - US
- **Block 26** (537-698 MHz) - US

### Wisycom
- **Band IV** (470-608 MHz) - EU
- **Band V** (608-698 MHz) - EU
- **UHF Full Range** (470-698 MHz) - EU

### Audio-Technica
- **DE2 Range** (470-530 MHz) - EU
- **EE1 Range** (530-590 MHz) - EU
- **DE1 Range** (470-698 MHz) - EU

### Sony
- **J Range** (782-806 MHz) - EU
- **K Range** (806-810 MHz) - EU
- **UHF Range** (470-806 MHz) - EU

## Adding Custom Band Plans

To add new standard band plans to the registry:

1. Edit `micboard/fixtures/band_plans.yaml`
2. Add entry under manufacturer section:

```yaml
manufacturer_code:
  band_key:
    name: "Display Name (Min-Max MHz)"
    min_mhz: 470.0
    max_mhz: 534.0
    region: "US/EU"  # Optional
```

3. Restart Django server to load new fixture data

## Programmatic Usage

### Get Available Band Plans
```python
from micboard.models.device_specs import get_available_band_plans

# Get all band plans for a manufacturer
plans = get_available_band_plans(manufacturer="shure")
# Returns: [("g50", "G50 (470-534 MHz)"), ("h50", "H50 (534-598 MHz)"), ...]
```

### Lookup Specific Band Plan
```python
from micboard.models.device_specs import get_band_plan

plan = get_band_plan(manufacturer="shure", band_plan_key="g50")
# Returns: {"name": "G50 (470-534 MHz)", "min_mhz": 470.0, "max_mhz": 534.0, "region": "US/EU"}
```

### Parse from Name String
```python
from micboard.models.device_specs import parse_band_plan_from_name

result = parse_band_plan_from_name(name="G50 (470-534 MHz)")
# Returns: {"min_mhz": 470.0, "max_mhz": 534.0}
```

### Model Method
```python
chassis = WirelessChassis.objects.get(pk=1)

# Get available band plans for this chassis's manufacturer
available = chassis.get_available_band_plans()
# Returns: [("g50", "G50 (470-534 MHz)"), ...]
```

## Implementation Details

### Save Hook Logic
```python
# In WirelessChassis.save()
if self.band_plan_name and self.manufacturer:
    # 1. Try registry lookup
    band_plan = get_band_plan(manufacturer=mfg_code, band_plan_key=band_key)
    if band_plan:
        self.band_plan_min_mhz = band_plan["min_mhz"]
        self.band_plan_max_mhz = band_plan["max_mhz"]
    # 2. Fall back to name parsing
    elif not self.band_plan_min_mhz or not self.band_plan_max_mhz:
        parsed = parse_band_plan_from_name(name=self.band_plan_name)
        if parsed:
            self.band_plan_min_mhz = parsed["min_mhz"]
            self.band_plan_max_mhz = parsed["max_mhz"]
```

### Order of Precedence
1. **Registry lookup** (from `band_plans.yaml`)
2. **Name string parsing** (regex: `"(\d+)-(\d+) MHz"`)
3. **Manual values** (if already set, not overwritten)

## Benefits

✅ **Consistency** - Standard band plans from registry ensure correct frequencies
✅ **Speed** - No manual entry for dozens/hundreds of chassis
✅ **Accuracy** - Eliminates typos in frequency ranges
✅ **Flexibility** - Still supports custom/manual entries when needed
✅ **Bulk Operations** - Can script band plan assignments via API/shell

## Bulk Update Example

Update all Shure ULXD4Q chassis to G50 band plan:

```python
from micboard.models import WirelessChassis

chassis_list = WirelessChassis.objects.filter(
    manufacturer__code="shure",
    model__icontains="ULXD4Q"
)

for chassis in chassis_list:
    chassis.band_plan_name = "G50 (470-534 MHz)"  # Frequencies auto-populate
    chassis.save()

print(f"Updated {chassis_list.count()} chassis to G50 band plan")
```

## API Integration

When syncing devices from manufacturer APIs, set `band_plan_name` and frequencies auto-populate:

```python
# In manufacturer plugin
chassis.band_plan_name = api_data.get("tuning_range")  # e.g., "G50 (470-534 MHz)"
chassis.save()  # min/max MHz auto-populated
```

## Validation

The regulatory compliance system validates that:
1. **Band plan range** is covered by regulatory data (chassis-level check)
2. **RF channel frequencies** fall within legal bands (channel-level check)

See [Regulatory Coverage Monitoring Guide](regulatory-coverage-monitoring.md) for details.
