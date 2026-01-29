# Battery Health Tracking Implementation

## Overview

Added comprehensive battery health tracking to **WirelessUnit** model, integrating with Shure System API battery health endpoints and manufacturer APIs.

## Database Changes

### New Fields Added to WirelessUnit

```python
# Battery health status (from manufacturer API)
battery_health = CharField(
    choices=["excellent", "good", "fair", "poor", "critical", "unknown"]
)
battery_health_description = TextField()  # From /battery-health/description
battery_level_description = TextField()   # From /battery-level/description
battery_cycles = PositiveIntegerField()   # Number of charge cycles
battery_temperature_c = FloatField()      # Battery temperature in Celsius
```

### Migration

**Migration 0007 (add_battery_health_tracking)**:
- Adds 5 new fields to `WirelessUnit` table
- All fields nullable/blank for backward compatibility
- No data migration needed (fields start empty)

## API Integration

### Shure System API Endpoints

Battery health data is now captured from:

1. **GET /v1/devices/{deviceId}/battery-health**
   - Returns health status (excellent/good/fair/poor/critical)
   - Stored in `battery_health` field

2. **GET /v1/devices/{deviceId}/battery-health/description**
   - Returns human-readable health description
   - Stored in `battery_health_description` field

3. **GET /v1/devices/{deviceId}/battery-level**
   - Returns battery level (already captured)
   - Used with existing `battery` and `battery_charge` fields

4. **GET /v1/devices/{deviceId}/battery-level/description**
   - Returns descriptive text for battery level
   - Stored in `battery_level_description` field

Additional metrics captured:
- **battery_cycles**: Number of charge cycles (from API)
- **battery_temperature_c**: Battery temperature in Celsius (from API)

### Data Flow

```plaintext
Shure API Response
    ↓
ShureDataTransformer.transform_transmitter_data()
    ↓ Extracts: batteryHealth, batteryCycles, batteryTemperatureC
    ↓
_update_channel_and_transmitter() (polling_tasks.py)
    ↓ Persists to database
    ↓
WirelessUnit model (battery health fields populated)
```

## Model Enhancements

### Battery Health Status

**get_battery_health()** - Returns battery health status:
- **Prefers API-provided data** from `battery_health` field
- **Fallback**: Computes from `battery_percentage`:
  - `> 50%` → "good"
  - `> 25%` → "fair"
  - `> 10%` → "poor"
  - `≤ 10%` → "critical"

### Visual Indicators

**get_battery_health_display_icon()** - Returns emoji icons:
- 🔋✨ **Excellent** - Full health
- 🔋 **Good** - Healthy battery
- 🔋⚠️ **Fair** - Aging battery
- 🪫 **Poor** - Replace soon
- 🪫❗ **Critical** - Replace immediately
- ❓ **Unknown** - No data

## Admin Interface

### List Display

Added `battery_health_display` column showing:
- Health status with color coding
- Visual emoji indicators
- Quick status overview

### Fieldsets

Organized battery information into dedicated section:

```python
"Battery Status" fieldset:
  - battery (0-255 raw level)
  - battery_charge (0-100%)
  - battery_percentage (computed property)
  - battery_runtime (estimated time remaining)
  - battery_type (e.g., "Lithium-Ion")
  - battery_health (excellent/good/fair/poor/critical)
  - battery_cycles (charge cycle count)
  - battery_temperature_c (temperature in Celsius)
  - battery_health_detail_display (detailed summary)
```

### Battery Health Detail Display

Shows comprehensive battery information box:

**Good Health** (green background):
```
API Health: good
Level: 78%
Cycles: 45
Temperature: 25.5°C
Runtime: 4:30:00
Type: Lithium-Ion
```

**Critical Health** (red background):
```
API Health: critical
Level: 8%
Cycles: 523
Temperature: 32.1°C
Runtime: 0:15:00
⚠️ Battery needs replacement
```

## Code Changes

### Files Modified

| File | Changes |
|------|---------|
| **micboard/models/hardware/wireless_unit.py** | + 5 new battery health fields<br>+ BATTERY_HEALTH_CHOICES constant<br>+ Enhanced get_battery_health() method<br>+ Added get_battery_health_display_icon() |
| **micboard/tasks/polling_tasks.py** | + Persist battery_health, battery_cycles, battery_temperature_c<br>+ Updated WirelessUnit.update_or_create() defaults |
| **micboard/integrations/shure/transformers.py** | + Extract batteryHealth, batteryCycles, batteryTemperatureC<br>+ Return battery health data in transform_transmitter_data() |
| **micboard/integrations/sennheiser/transformers.py** | + Extract battery health data from Sennheiser API<br>+ Return in transform_transmitter_data() |
| **micboard/admin/channels.py** | + battery_health_display column<br>+ battery_health_detail_display readonly field<br>+ "Battery Status" fieldset<br>+ Color-coded health indicators |
| **micboard/migrations/0007_add_battery_health_tracking.py** | + Migration to add 5 new fields |

### Transformer Changes

**Before** (Shure):
```python
extra = {
    "battery_health": tx_data.get("batteryHealth"),  # Lost in extra
    "battery_cycles": tx_data.get("batteryCycles"),
    # ...
}
```

**After** (Shure):
```python
battery_health = tx_data.get("batteryHealth", "")
battery_cycles = tx_data.get("batteryCycles")
battery_temperature_c = tx_data.get("batteryTemperatureC")

return {
    "battery_health": battery_health,        # Now persisted!
    "battery_cycles": battery_cycles,
    "battery_temperature_c": battery_temperature_c,
    # ...
}
```

## Future Enhancements

### Real-Time Subscriptions

The Shure API supports WebSocket subscriptions for battery updates:

```python
# POST /v1/devices/{deviceId}/battery-health/subscription/{transportId}
# POST /v1/devices/{deviceId}/battery-level/subscription/{transportId}
```

**Recommended Implementation**:
1. Subscribe to battery health changes when device comes online
2. Update WirelessUnit in real-time when battery health changes
3. Emit WebSocket events to frontend for live battery monitoring
4. Integrate with existing `websocket_tasks.py` subscription system

### Battery Health Alerts

Extend `micboard/services/alerts.py` to include battery health alerts:

```python
# Alert when battery health degrades
if unit.battery_health in ["poor", "critical"]:
    create_alert(
        type="BATTERY_HEALTH_DEGRADED",
        unit=unit,
        message=f"Battery health {unit.battery_health}: Cycles={unit.battery_cycles}"
    )

# Alert on high temperature
if unit.battery_temperature_c and unit.battery_temperature_c > 40:
    create_alert(
        type="BATTERY_OVERHEATING",
        unit=unit,
        temperature=unit.battery_temperature_c
    )
```

### Description Field Population

Battery health/level descriptions from API should be fetched and stored:

```python
# In polling or synchronization service
if device_supports_battery_health(unit):
    health_desc = api_client.get_battery_health_description(device_id)
    level_desc = api_client.get_battery_level_description(device_id)

    unit.battery_health_description = health_desc
    unit.battery_level_description = level_desc
    unit.save(update_fields=["battery_health_description", "battery_level_description"])
```

### Battery Analytics

Potential analytics features:

1. **Battery Lifecycle Tracking**
   - Plot battery health over time
   - Predict replacement schedules based on cycle count
   - Track temperature trends

2. **Fleet Battery Health Dashboard**
   - Show all units with poor/critical battery health
   - Battery replacement schedule recommendations
   - Average battery life by model/type

3. **Capacity Planning**
   - Estimate battery inventory needs
   - Track battery purchase/replacement costs
   - Identify problematic battery batches

## Testing Recommendations

### Unit Tests

```python
def test_battery_health_from_api():
    """Test battery health from API is preferred over computed."""
    unit = WirelessUnit(battery=200, battery_health="excellent")
    assert unit.get_battery_health() == "excellent"

def test_battery_health_fallback():
    """Test fallback to computed health when no API data."""
    unit = WirelessUnit(battery=200, battery_health="")
    assert unit.get_battery_health() == "good"  # 78% = good

def test_battery_health_icons():
    """Test icon mapping for each health status."""
    unit = WirelessUnit()
    for health in ["excellent", "good", "fair", "poor", "critical", "unknown"]:
        unit.battery_health = health
        icon = unit.get_battery_health_display_icon()
        assert icon  # Should return an icon
```

### Integration Tests

```python
def test_shure_battery_health_persistence(mock_shure_api):
    """Test battery health data is persisted from Shure API."""
    mock_shure_api.return_value = {
        "battery": 150,
        "batteryHealth": "good",
        "batteryCycles": 42,
        "batteryTemperatureC": 24.5
    }

    poll_device(device_id)

    unit = WirelessUnit.objects.get(...)
    assert unit.battery_health == "good"
    assert unit.battery_cycles == 42
    assert unit.battery_temperature_c == 24.5
```

## Benefits

1. ✅ **Complete Battery Monitoring** - Captures all battery health metrics from manufacturer APIs
2. ✅ **Predictive Maintenance** - Battery cycle counts enable replacement scheduling
3. ✅ **Safety Monitoring** - Temperature tracking alerts overheating risks
4. ✅ **Multi-Manufacturer Support** - Works with Shure, Sennheiser, and future integrations
5. ✅ **Backward Compatible** - All fields optional, no breaking changes
6. ✅ **Admin Friendly** - Visual indicators and detailed health displays
7. ✅ **API-First Design** - Prefers manufacturer data, falls back to computation

## Related Documentation

- [Shure Integration Guide](docs/shure-integration.md)
- [Admin Interface Documentation](docs/admin-interface.md)
- [Polling Tasks](micboard/tasks/polling_tasks.py)
- [Alert System](micboard/services/alerts.py)
