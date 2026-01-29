# Manufacturer-Agnostic DiscoveredDevice Refactoring

## Summary

Refactored `DiscoveredDevice` model and related services to support **multiple manufacturers** (Shure, Sennheiser, Audio-Technica, etc.) with different API structures and device state models.

## Problem Identified

The previous implementation had **Shure-specific hardcoded fields**:
- `compatibility` field with Shure enums (`INCOMPATIBLE_TOO_OLD`, `COMPATIBLE_LATEST`, etc.)
- `device_state` field with Shure states (`ONLINE`, `DISCOVERED`, `ERROR`, etc.)
- `communication_protocol` field for Shure protocol names
- Comments and help text mentioning "Shure API", "P300", "AD4Q", etc.

This design **wouldn't work** for:
- **Sennheiser SSCv2 API** (different device structure, different state model)
- **Audio-Technica** or other future manufacturers
- Any manufacturer with different compatibility/state semantics

## Solution: Manufacturer-Agnostic Design

### 1. Generic Status Field

Replaced manufacturer-specific fields with a **universal status enum**:

```python
STATUS_READY = "ready"           # Device is online and ready to manage
STATUS_PENDING = "pending"       # Device discovered but not yet ready
STATUS_INCOMPATIBLE = "incompatible"  # Firmware/API version mismatch
STATUS_ERROR = "error"           # Communication error
STATUS_OFFLINE = "offline"       # Device is offline
STATUS_UNKNOWN = "unknown"       # Status not determined
```

### 2. Metadata JSONField

All manufacturer-specific data now stored in `metadata` JSONField:

**Shure System API Example:**
```json
{
  "compatibility": "COMPATIBLE_LATEST",
  "deviceState": "ONLINE",
  "hardwareIdentity": {
    "deviceId": "uuid-here",
    "serialNumber": "SN12345"
  },
  "softwareIdentity": {
    "model": "P300",
    "firmwareVersion": "1.2.3"
  },
  "communicationProtocol": {
    "name": "MQTT",
    "version": "3.1.1"
  }
}
```

**Sennheiser SSCv2 API Example:**
```json
{
  "deviceModel": "EW-DX",
  "deviceSerial": "S12345",
  "firmwareVersion": "2.0.1",
  "status": "active",
  "networkInterface": {
    "mac": "00:11:22:33:44:55"
  }
}
```

### 3. Manufacturer-Aware Helper Methods

The model provides manufacturer-specific accessors:

```python
device.get_shure_compatibility()      # Returns Shure compatibility string
device.get_shure_device_state()       # Returns Shure deviceState
device.get_communication_protocol()   # Returns protocol name (works for Shure)
```

Other manufacturers can add similar helpers:
```python
device.get_sennheiser_status()
device.get_audio_technica_network_state()
```

### 4. Discovery Service Mapping

`DiscoveryOrchestrationService._persist_discovered_devices()` now:

1. **Detects manufacturer API structure** (Shure vs. Sennheiser vs. other)
2. **Extracts common fields** (ip, device_type, model, channels)
3. **Maps manufacturer states to generic status**
4. **Stores all manufacturer-specific data in metadata**

**Shure Mapping:**
```python
if compatibility in {"INCOMPATIBLE_TOO_OLD", "INCOMPATIBLE_TOO_NEW"}:
    generic_status = STATUS_INCOMPATIBLE
elif deviceState == "ONLINE":
    generic_status = STATUS_READY
elif deviceState == "DISCOVERED":
    generic_status = STATUS_PENDING
# ...
```

**Sennheiser/Other Mapping:**
```python
if device_status in {"online", "ready", "active"}:
    generic_status = STATUS_READY
elif device_status in {"offline", "inactive"}:
    generic_status = STATUS_OFFLINE
# ...
```

### 5. Admin Interface Updates

**Before (Shure-specific):**
- `compatibility_status_display` - showed Shure compatibility
- `device_state_display` - showed Shure device state
- `communication_protocol` column

**After (Manufacturer-agnostic):**
- `status_display_with_color` - shows generic status with icons
- `protocol_display` - extracts protocol from metadata
- Works for all manufacturers

Visual indicators now map to generic status:
- ✅ Ready to Manage (green)
- 🔍 Pending (orange)
- ⚠️ Incompatible (red)
- ✕ Error (red)
- 📴 Offline (gray)

## Database Migrations

### Migration 0004 (OLD - Shure-specific)
```python
# Added Shure-specific fields
+ device_state (choices: ONLINE, OFFLINE, ERROR, DISCOVERED)
+ compatibility (choices: INCOMPATIBLE_TOO_OLD, COMPATIBLE_LATEST, etc.)
+ communication_protocol (CharField)
```

### Migration 0005 (NEW - Manufacturer-agnostic)
```python
# Removed Shure-specific fields
- device_state
- compatibility
- communication_protocol

# Added generic fields
+ status (choices: ready, pending, incompatible, error, offline, unknown)
+ metadata (JSONField - stores manufacturer-specific data)
```

### Migration 0006 (Data Migration)
```python
# Migrated existing Shure devices
OLD: device_state="ONLINE", compatibility="COMPATIBLE_LATEST"
NEW: status="ready", metadata={"deviceState": "ONLINE", "compatibility": "COMPATIBLE_LATEST"}
```

## Files Modified

| File | Changes |
|------|---------|
| `micboard/models/discovery/registry.py` | - Replaced Shure enums with generic STATUS_* constants<br>- Added `metadata` JSONField<br>- Added manufacturer-specific helper methods<br>- Updated `is_manageable()` logic<br>- Updated `get_incompatibility_reason()` to check metadata |
| `micboard/admin/monitoring.py` | - Replaced `compatibility_status_display()` with `status_display_with_color()`<br>- Removed `device_state_display()`<br>- Added `protocol_display()` to extract from metadata<br>- Updated list_display and list_filter<br>- Updated fieldsets to show `metadata` and `status` |
| `micboard/services/discovery_orchestration_service.py` | - Refactored `_persist_discovered_devices()` to detect manufacturer structure<br>- Maps Shure API to generic status + metadata<br>- Maps Sennheiser/other APIs to generic status + metadata<br>- Stores all manufacturer-specific fields in metadata JSONField |
| `micboard/migrations/0005_*.py` | Schema migration (remove old fields, add new fields) |
| `micboard/migrations/0006_*.py` | Data migration (convert existing devices to new structure) |

## Backward Compatibility

### For Shure Devices
✅ **Fully compatible** - all Shure-specific data preserved in metadata:
- `metadata.compatibility` = old `compatibility` field
- `metadata.deviceState` = old `device_state` field
- `metadata.communicationProtocol.name` = old `communication_protocol` field

Helper methods provide easy access:
```python
device.get_shure_compatibility()  # Returns "COMPATIBLE_LATEST"
device.get_shure_device_state()   # Returns "ONLINE"
```

### For New Manufacturers
✅ **Fully extensible** - any manufacturer can now be supported:

1. Add discovery logic in manufacturer plugin
2. Return device data in any structure
3. Persistence service stores it in metadata
4. Add manufacturer-specific helper methods as needed

## Testing Recommendations

### Unit Tests
- Test status mapping for all manufacturers (Shure, Sennheiser, unknown)
- Test metadata extraction for different API structures
- Test helper methods (`get_shure_compatibility()`, etc.)
- Test `is_manageable()` with different status values

### Integration Tests
- Test discovery with Shure System API (should populate metadata correctly)
- Test discovery with Sennheiser SSCv2 API (should handle different structure)
- Test admin display for both manufacturers
- Test promotion workflow for devices from different manufacturers

## Future Enhancements

### Add More Manufacturer Helpers
```python
# In DiscoveredDevice model
def get_sennheiser_network_info(self) -> dict:
    return self.metadata.get("networkInterface", {})

def get_audio_technica_codec_info(self) -> dict:
    return self.metadata.get("codecInfo", {})
```

### Manufacturer-Specific Status Logic
Consider moving status mapping to manufacturer plugins:

```python
# In ShurePlugin
def map_device_status(self, device_data: dict) -> str:
    if device_data["compatibility"] in {"INCOMPATIBLE_TOO_OLD", ...}:
        return DiscoveredDevice.STATUS_INCOMPATIBLE
    # ...

# In SennheiserPlugin
def map_device_status(self, device_data: dict) -> str:
    if device_data["status"] == "active":
        return DiscoveredDevice.STATUS_READY
    # ...
```

### API Documentation
Document metadata structure for each manufacturer in API docs:
- Shure metadata schema
- Sennheiser metadata schema
- Generic fallback schema

## Benefits

1. ✅ **Multi-Manufacturer Support** - Shure, Sennheiser, and future manufacturers work seamlessly
2. ✅ **No Data Loss** - All manufacturer-specific data preserved in metadata
3. ✅ **Type Safety** - Generic status enum provides consistent interface
4. ✅ **Backward Compatible** - Existing Shure devices migrated automatically
5. ✅ **Extensible** - Easy to add new manufacturers without model changes
6. ✅ **Admin Friendly** - Visual status indicators work for all manufacturers
7. ✅ **Query Friendly** - Generic status field is indexed and filterable

## Related Documentation

- [Shure Integration Guide](docs/shure-integration.md)
- [Manufacturer Plugin Architecture](docs/development/manufacturer-plugins.md)
- [Discovery System Overview](docs/guides/discovery-system.md)
