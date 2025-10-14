# Shure System API Compatibility Refactoring

## Overview

This document details the significant refactoring completed on **October 14, 2025** to ensure full compatibility with the Shure System API. The refactoring addresses critical issues in API communication, data transformation, error handling, and model structure.

## Major Changes

### 1. API Client Improvements (`shure_api_client.py`)

#### Missing Import Fixed
- **Issue**: `json` module was used but never imported, causing runtime errors in WebSocket handling
- **Fix**: Added `from __future__ import annotations` and `import json` at module top

#### Type Hints Modernization
- Updated all type hints to use PEP 604 union syntax (`X | None` instead of `Optional[X]`)
- Removed unnecessary `Callable` and `Optional` imports
- Added proper return type annotations for all methods

#### Enhanced Error Handling
- Added `json.JSONDecodeError` handling in `_make_request()`
- Improved WebSocket message parsing with try/except blocks
- Added comprehensive logging at DEBUG, INFO, and ERROR levels
- Truncated error messages to prevent log spam

#### Improved Rate Limiting
- Fixed logging in `rate_limit` decorator to use parameterized format (prevents f-string issues)
- Added better debug logging for rate limit operations

#### Better Data Transformation

##### New `_transform_transmitter_data()` Method
```python
def _transform_transmitter_data(self, tx_data: dict, channel_num: int) -> dict | None
```
- Handles various Shure API field name variations:
  - `battery_bars` vs `batteryBars`
  - `battery_charge` vs `batteryCharge`
  - `audio_level` vs `audioLevel`
  - etc.
- Provides sensible defaults for all fields
- Returns `None` on transformation errors with proper logging
- Properly handles `battery_charge` field from newer devices

##### Enhanced `_transform_device_data()` Method
- Better error handling with null checks
- Comprehensive logging at each transformation step
- Handles missing/optional fields gracefully
- Only adds channels with valid transmitter data
- Logs warnings for devices without transmitter data

##### Improved Device Type Mapping
```python
def _map_device_type(api_type: str) -> str
```
- Handles multiple naming conventions:
  - `AXIENT_DIGITAL`, `AXIENTDIGITAL`, `AXTD`, `AD` → `axtd`
  - `UHF-R`, `UHF_R`, `UHFR` → `uhfr`
  - `QLX-D`, `QLX_D`, `QLXD` → `qlxd`
- Case-insensitive matching
- Handles spaces and hyphens in type names

#### WebSocket Improvements
- Better error handling for initial `transportId` message
- Graceful handling of malformed WebSocket messages
- Continues operation even if individual messages fail to parse
- Improved logging with device ID context
- Proper exception chaining with `from None` to avoid noise

#### Request Logging
- All API requests now logged with method and URL
- Success responses logged at DEBUG level
- Errors logged with truncated response text (200 char limit)
- Added request/response timing context

### 2. Model Updates (`models/devices.py`)

#### New `battery_charge` Field on Transmitter
```python
battery_charge = models.PositiveIntegerField(
    null=True,
    blank=True,
    help_text="Battery charge percentage (0-100, optional field from newer devices)",
)
```
- Supports newer Shure devices that report battery as percentage
- Nullable field (older devices don't provide this)
- Complements existing `battery` field (which uses bars/255 scale)

### 3. Polling Command Improvements (`poll_devices.py`)

#### Intelligent Slot Assignment
The refactored `update_models()` method includes sophisticated slot management:

1. **Reuse Existing Slots**: If a transmitter already exists for a channel, keep its slot
2. **API-Provided Slots**: Use slot from API if provided
3. **Deterministic Generation**: Generate consistent slots based on `device_id-channel` hash
4. **Collision Detection**: Check for slot conflicts and increment if needed
5. **Slot Range**: Uses 0-9999 range for manageable slot numbers

```python
# Example slot assignment logic
base_slot = hash(f"{receiver.api_device_id}-{channel_num}")
target_slot = abs(base_slot) % 10000

# Check for collisions
while Transmitter.objects.filter(slot=target_slot).exists():
    target_slot = (target_slot + 1) % 10000
```

#### Enhanced Model Updates
- Added logging for new receiver/channel creation
- Proper handling of `battery_charge` field
- Better offline device detection with warning logs
- Comprehensive exception handling per device

#### Improved Broadcasting
- Added `battery_charge` to WebSocket broadcast data
- Ensures frontend gets complete transmitter state

### 4. Database Migration

Created `0002_transmitter_battery_charge.py`:
- Adds `battery_charge` field to existing Transmitter model
- Nullable field (won't break existing data)
- Can be run on existing installations

## API Field Mappings

### Device Fields
| Shure API Field | Micboard Field | Notes |
|----------------|----------------|-------|
| `id` | `api_device_id` | Unique device identifier |
| `ip_address` / `ipAddress` | `ip` | Device IP address |
| `type` | `device_type` | Mapped through `_map_device_type()` |
| `model_name` / `modelName` | `name` | Device model name |
| `firmware_version` / `firmwareVersion` | `firmware_version` | Firmware version string |

### Transmitter Fields
| Shure API Field | Micboard Field | Default | Notes |
|----------------|----------------|---------|-------|
| `battery_bars` / `batteryBars` | `battery` | 255 | Battery level (0-255) |
| `battery_charge` / `batteryCharge` | `battery_charge` | NULL | Battery percentage (0-100) |
| `battery_runtime_minutes` / `batteryRuntimeMinutes` | `runtime` | "" | Formatted as HH:MM |
| `audio_level` / `audioLevel` | `audio_level` | 0 | Audio level in dB |
| `rf_level` / `rfLevel` | `rf_level` | 0 | RF signal level |
| `audio_quality` / `audioQuality` | `quality` | 255 | Signal quality (0-255) |
| `tx_offset` / `txOffset` | `tx_offset` | 255 | Transmitter offset |
| `frequency` | `frequency` | "" | Operating frequency |
| `antenna` | `antenna` | "" | Antenna information |
| `status` | `status` | "" | Transmitter status |
| `name` / `deviceName` | `name`, `name_raw` | "" | Transmitter name |
| `slot` | `slot` | generated | Slot assignment |

## Error Recovery

### Graceful Degradation
- Individual device errors don't stop entire poll
- WebSocket message parse errors don't kill connection
- Missing fields use sensible defaults
- Malformed data logged but processing continues

### Logging Strategy
- **DEBUG**: Request/response details, field mappings
- **INFO**: Device creation, successful operations, WebSocket connections
- **WARNING**: Missing optional fields, offline devices, slot generation
- **ERROR**: HTTP errors, connection failures, transformation failures
- **EXCEPTION**: Unexpected errors with full stack traces

## Testing Recommendations

### 1. Test with Real Shure System API
```bash
# Configure your Shure System API endpoint
export SHURE_API_BASE_URL="http://your-shure-server:8080"
export SHURE_API_USERNAME="admin"  # if needed
export SHURE_API_PASSWORD="password"  # if needed

# Run initial poll test
python manage.py poll_devices --initial-poll-only

# Run with WebSocket subscriptions
python manage.py poll_devices
```

### 2. Verify Database Updates
```bash
# Check created receivers
python manage.py shell
>>> from micboard.models import Receiver, Channel, Transmitter
>>> Receiver.objects.all()
>>> Channel.objects.all()
>>> Transmitter.objects.all()
```

### 3. Monitor Logs
```bash
# Watch logs for errors
tail -f /var/log/django/micboard.log

# Or if using console logging
python manage.py poll_devices | tee poll_output.log
```

### 4. Test Different Device Types
- ULX-D receivers
- QLX-D receivers
- UHF-R receivers  
- Axient Digital receivers
- PSM 1000 (P10T) systems

Verify each device type is correctly identified and all fields are populated.

## Migration Path

### For Existing Installations

1. **Backup Database**
   ```bash
   python manage.py dumpdata micboard > backup.json
   ```

2. **Run Migration**
   ```bash
   python manage.py migrate micboard
   ```

3. **Verify Migration**
   ```bash
   python manage.py showmigrations micboard
   # Should show: [X] 0002_transmitter_battery_charge
   ```

4. **Test Polling**
   ```bash
   python manage.py poll_devices --initial-poll-only
   ```

5. **Check for Errors**
   - Review logs for any transformation errors
   - Verify all devices are detected
   - Confirm battery data is populating

### For New Installations

Simply run:
```bash
python manage.py migrate
python manage.py poll_devices
```

## Known Limitations

1. **Slot Assignment**: Generated slots are deterministic but may change if receiver IDs change
2. **WebSocket Subscriptions**: Each device gets its own WebSocket connection (could be optimized)
3. **Field Name Variations**: We handle common variations but Shure may introduce new field names
4. **Battery Reporting**: Older devices only report `battery_bars`, newer devices add `battery_charge`

## Future Improvements

### Short Term
1. Add support for control commands (not just monitoring)
2. Implement WebSocket multiplexing (one connection, multiple subscriptions)
3. Add API response caching for better performance

### Medium Term
1. Add support for Shure Wireless Workbench integration
2. Implement historical data storage
3. Add alerting system for low battery/RF issues

### Long Term
1. Support for multiple Shure System API servers
2. Load balancing for high-volume deployments
3. Plugin system for custom device types

## Rollback Plan

If issues are encountered:

1. **Revert Code Changes**
   ```bash
   git revert <commit-hash>
   ```

2. **Rollback Migration**
   ```bash
   python manage.py migrate micboard 0001
   ```

3. **Restore Database** (if needed)
   ```bash
   python manage.py loaddata backup.json
   ```

## Support

For issues related to:
- **Shure System API**: Contact Shure support or consult [Shure API Documentation](https://shure.stoplight.io)
- **Django Micboard**: Open an issue on GitHub
- **Database Issues**: Check Django migration documentation

## Changelog Summary

### Added
- `battery_charge` field to Transmitter model
- `_transform_transmitter_data()` method for better data handling
- Comprehensive logging throughout API client
- JSON parsing error handling
- Field name variation handling

### Changed
- All type hints to use PEP 604 union syntax
- `_transform_device_data()` for better error handling
- `_map_device_type()` to handle more device type variations
- Slot assignment to be more intelligent and collision-resistant
- WebSocket error handling to be non-fatal
- Logging format to use parameterized strings

### Fixed
- Missing `json` import in `shure_api_client.py`
- F-string usage in logging statements (now parameterized)
- Rate limiter logging format
- WebSocket message parsing errors
- Slot collision issues
- Missing `battery_charge` in broadcasts

## Version Information

- **Refactoring Date**: October 14, 2025
- **Django Version**: 4.2+
- **Python Version**: 3.9+
- **Shure System API**: Compatible with latest version

## Contributors

This refactoring was completed to address production issues and improve reliability when interfacing with Shure System API servers. Special thanks to the original Micboard project for the foundation.
