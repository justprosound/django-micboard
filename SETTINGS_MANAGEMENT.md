# Settings Management System

The settings management system allows administrators to configure the entire application without editing code. It supports a multi-tenant scope hierarchy ensuring flexibility across different organizational structures.

## Architecture

### Settings Models

#### `SettingDefinition`
Defines available settings system-wide. Each definition includes:
- **key**: Unique identifier (e.g., `battery_low_threshold`)
- **label**: Human-readable name
- **description**: Detailed explanation
- **scope**: Where this setting can be configured (GLOBAL, ORGANIZATION, SITE, MANUFACTURER)
- **type**: Data type (string, integer, boolean, json, choices)
- **default_value**: Fallback if no specific value configured
- **choices_json**: For dropdown types, the available options

#### `Setting`
Actual configured values per scope. Includes foreign keys to:
- `definition` (required): Which setting this is
- `organization` (optional): Organization-specific setting
- `site` (optional): Site-specific setting
- `manufacturer` (optional): Manufacturer-specific setting

The combination of (definition, organization, site, manufacturer) must be unique.

### SettingsRegistry Service

The `SettingsRegistry` service provides unified access to configured settings with intelligent fallback:

```python
from micboard.services.settings_registry import SettingsRegistry

# Get battery low threshold, resolving through scope hierarchy
threshold = SettingsRegistry.get(
    'battery_low_threshold',
    default=20,
    organization=org,
    site=site,
    manufacturer=shure_mfg
)
# Resolution order:
# 1. manufacturer-specific setting
# 2. site-specific setting
# 3. organization-specific setting
# 4. global setting
# 5. definition default
# 6. function default (20)
```

The registry includes:
- **Automatic caching**: 5-minute TTL on values, LRU on definitions
- **Type conversion**: Automatically parses string values to correct types
- **Cache invalidation**: Called automatically when settings are updated

### ManufacturerConfigRegistry Service

Quick access to manufacturer configurations with database overrides:

```python
from micboard.services.manufacturer_config_registry import ManufacturerConfigRegistry

config = ManufacturerConfigRegistry.get('shure', manufacturer=shure_mfg)
# Returns: ManufacturerConfig with:
# - battery thresholds
# - health check intervals
# - API timeouts
# - feature flags
# - device roles per status
# With any database overrides applied
```

## Usage

### Initialize Settings

Before using the settings system, initialize the database with setting definitions:

```bash
python manage.py init_settings
python manage.py init_settings --manufacturer-defaults  # Also initialize defaults
python manage.py init_settings --reset  # Clear and reinitialize
```

### Admin Interface

#### Via Django Admin

1. **Go to**: `/admin/micboard/settingdefinition/`
   - View all available settings
   - Filter by scope or type
   - Mark settings as active/inactive

2. **Configure Values**:
   - Go to `/admin/micboard/setting/`
   - Click "Add" to create a new configuration
   - Select the setting definition
   - Choose scope (global, organization, site, manufacturer)
   - Enter the value (automatically validated by type)

#### Bulk Configuration View

For rapid configuration of multiple settings:

1. **Go to**: `/admin/settings/bulk/`
2. **Select scope** where settings apply
3. **Fill in values** for any settings you want to configure
4. **Save** - all will be updated at once

#### Manufacturer Configuration View

Quick setup for manufacturer-specific settings:

1. **Go to**: `/admin/settings/manufacturer/`
2. **Select manufacturer** to configure
3. **Enter values** for battery thresholds, API timeouts, etc.
4. **Save** - all updates applied to that manufacturer

#### Settings Overview

View all configured settings:

1. **Go to**: `/admin/settings/`
2. **See settings** grouped by scope
3. **Click to edit** any specific setting

### In Code

Access settings in your services and views:

```python
from micboard.services.settings_registry import SettingsRegistry

class DevicePollingService:
    def poll(self, device):
        interval = SettingsRegistry.get(
            'polling_interval_seconds',
            default=300,
            organization=device.site.organization,
            site=device.site
        )

        if interval:
            schedule.every(interval).seconds.do(self.poll_device)
```

## Scope Hierarchy

Settings are resolved in this order:
1. **Most Specific**: Manufacturer > Site > Organization > Global
2. **Fallback**: Definition default > Function default
3. **Required**: Raises error if marked required and not found

Example for manufacturer settings:
```
Manufacturer Setting (if exists)
  ↓ (if not, fallback to)
Site Setting (if exists)
  ↓ (if not, fallback to)
Organization Setting (if exists)
  ↓ (if not, fallback to)
Global Setting (if exists)
  ↓ (if not, fallback to)
SettingDefinition default
```

## Standard Settings

### Battery Management (Manufacturer)
- `battery_good_level`: Good condition threshold (0-100%)
- `battery_low_level`: Low battery alert threshold (0-100%)
- `battery_critical_level`: Critical threshold (0-100%)

### Health Checks (Manufacturer)
- `health_check_interval`: Seconds between API health checks
- `supports_health_check`: Whether manufacturer has health API

### API Configuration (Manufacturer)
- `api_timeout`: Request timeout in seconds
- `device_max_requests_per_call`: Max devices per API request
- `supports_discovery_ips`: Whether IP discovery is supported

### Discovery (Organization)
- `discovery_enabled`: Enable auto-discovery
- `discovery_interval_minutes`: How often to discover

### Polling (Organization)
- `polling_enabled`: Enable auto-polling
- `polling_interval_seconds`: How often to poll devices
- `polling_batch_size`: Devices per batch

### Caching (Global)
- `cache_device_specs_minutes`: Device spec cache TTL
- `cache_settings_minutes`: Settings value cache TTL

### Monitoring (Organization)
- `log_api_calls`: Log all API interactions
- `alert_on_device_offline_minutes`: Alert threshold for offline devices

## Adding New Settings

### 1. Define in Initialization

Edit `micboard/management/commands/init_settings.py` and add to the `_initialize_definitions` method:

```python
{
    'key': 'my_setting_key',
    'label': 'My Setting Label',
    'description': 'What this setting controls',
    'scope': SettingDefinition.SCOPE_ORGANIZATION,  # or other scope
    'setting_type': SettingDefinition.TYPE_BOOLEAN,
    'default_value': 'true',
    'required': False,
}
```

### 2. Register and Run Migration

```bash
python manage.py init_settings --reset
```

### 3. Use in Code

```python
from micboard.services.settings_registry import SettingsRegistry

value = SettingsRegistry.get('my_setting_key', default=False, organization=org)
```

## Type System

| Type | Example | Usage |
|------|---------|-------|
| `string` | `"value"` | Text settings |
| `integer` | `300` | Numeric config (timeouts, thresholds) |
| `boolean` | `true` / `false` | Feature flags |
| `json` | `{"key": "value"}` | Complex structures |
| `choices` | Admin dropdown | Fixed set of options |

## Caching

The settings system caches aggressively for performance:

- **Definition Cache**: LRU, all definitions cached at startup
- **Value Cache**: 5-minute TTL, per-setting basis
- **Automatic Invalidation**: Cache cleared when setting is updated via admin

Manual cache invalidation:
```python
SettingsRegistry.invalidate_cache('battery_low_threshold')  # Specific setting
SettingsRegistry.invalidate_cache()  # All settings
```

## Troubleshooting

### Settings Not Updating

1. Check cache isn't stale: `SettingsRegistry.invalidate_cache(key)`
2. Verify scope: Default is GLOBAL, check if organization/site/manufacturer needed
3. Check definition exists: `SettingDefinition.objects.filter(key='my_key').exists()`

### Type Validation Errors

Settings are validated by type before saving:
- **Integer**: Must be valid number
- **Boolean**: Use true/false (case-insensitive)
- **Choices**: Must be a valid key from choices_json
- **JSON**: Must be valid JSON

### Performance

- Settings are cached by default (5 minutes)
- Bulk operations should be batched
- For real-time updates, use `invalidate_cache()`

## Best Practices

1. **Use appropriate scope**: Manufacturer settings for device config, Organization for policies
2. **Provide defaults**: Always include defaults for backward compatibility
3. **Document settings**: Use clear labels and descriptions
4. **Cache invalidation**: Remember to invalidate after programmatic updates
5. **Type safety**: Match function default types to setting type
6. **Validation**: Use choices type for predefined valid values
