# Settings Integration Guide

This guide shows how to integrate the new settings system with existing services, eliminating hardcoded constants and enabling admin configurability.

## 1. Device Polling Service

### Before
```python
# poll_devices.py - hardcoded constants scattered throughout
class DevicePollingService:
    POLLING_INTERVAL = 300  # seconds
    BATCH_SIZE = 50

    def poll(self, organization):
        while True:
            time.sleep(self.POLLING_INTERVAL)
            # poll devices...
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry

class DevicePollingService:
    def poll(self, organization):
        interval = SettingsRegistry.get(
            'polling_interval_seconds',
            default=300,
            organization=organization
        )
        batch_size = SettingsRegistry.get(
            'polling_batch_size',
            default=50,
            organization=organization
        )

        while True:
            time.sleep(interval)
            # poll devices in batches of batch_size...
```

## 2. Battery Health Monitoring

### Before
```python
# services/hardware.py - manufacturer-specific logic scattered
class BatteryHealthMonitor:
    BATTERY_THRESHOLDS = {
        'shure': {'good': 90, 'low': 20, 'critical': 0},
        'sennheiser': {'good': 85, 'low': 25, 'critical': 5},
    }

    def check_battery_status(self, device):
        manufacturer = device.manufacturer.code
        if manufacturer not in self.BATTERY_THRESHOLDS:
            return 'unknown'

        thresholds = self.BATTERY_THRESHOLDS[manufacturer]
        battery_level = device.battery_level

        if battery_level >= thresholds['good']:
            return 'good'
        elif battery_level >= thresholds['low']:
            return 'low'
        else:
            return 'critical'
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry

class BatteryHealthMonitor:
    def check_battery_status(self, device):
        good_level = SettingsRegistry.get(
            'battery_good_level',
            default=90,
            manufacturer=device.manufacturer
        )
        low_level = SettingsRegistry.get(
            'battery_low_level',
            default=20,
            manufacturer=device.manufacturer
        )

        battery_level = device.battery_level

        if battery_level >= good_level:
            return 'good'
        elif battery_level >= low_level:
            return 'low'
        else:
            return 'critical'
```

## 3. API Client Configuration

### Before
```python
# services/polling_api.py - hardcoded timeouts
class ShureAPIClient:
    TIMEOUT = 30
    MAX_DEVICES_PER_CALL = 100

    def get_devices(self, ip_list):
        response = requests.get(
            url,
            timeout=self.TIMEOUT,
            params={'ips': ip_list[:self.MAX_DEVICES_PER_CALL]}
        )
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry

class ShureAPIClient:
    def __init__(self, manufacturer):
        self.manufacturer = manufacturer

    def get_devices(self, ip_list):
        timeout = SettingsRegistry.get(
            'api_timeout',
            default=30,
            manufacturer=self.manufacturer
        )
        max_per_call = SettingsRegistry.get(
            'device_max_requests_per_call',
            default=100,
            manufacturer=self.manufacturer
        )

        response = requests.get(
            url,
            timeout=timeout,
            params={'ips': ip_list[:max_per_call]}
        )
```

## 4. Discovery Service

### Before
```python
# services/discovery.py - feature flags hardcoded
class DiscoveryService:
    SUPPORTED_FEATURES = {
        'shure': {'discovery_ips': True, 'health_check': True},
        'sennheiser': {'discovery_ips': False, 'health_check': True},
    }

    def discover(self, manufacturer):
        if self.SUPPORTED_FEATURES[manufacturer.code]['discovery_ips']:
            # Use IP-based discovery
            self._discover_by_ip()
        else:
            # Use other method
            self._discover_by_registry()
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry

class DiscoveryService:
    def discover(self, manufacturer):
        supports_ips = SettingsRegistry.get(
            'supports_discovery_ips',
            default=False,
            manufacturer=manufacturer
        )

        if supports_ips:
            # Use IP-based discovery
            self._discover_by_ip()
        else:
            # Use other method
            self._discover_by_registry()
```

## 5. Health Check Service

### Before
```python
# services/health.py - hardcoded intervals
class HealthCheckService:
    INTERVAL_SECONDS = 300
    SUPPORTED = {
        'shure': True,
        'sennheiser': True,
    }

    def schedule_health_checks(self, organization):
        while True:
            time.sleep(self.INTERVAL_SECONDS)
            # perform health checks...
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry

class HealthCheckService:
    def schedule_health_checks(self, organization):
        while True:
            interval = SettingsRegistry.get(
                'health_check_interval',
                default=300,
                organization=organization
            )
            time.sleep(interval)
            # perform health checks...

    def is_supported(self, manufacturer):
        return SettingsRegistry.get(
            'supports_health_check',
            default=False,
            manufacturer=manufacturer
        )
```

## 6. Device Role/Status Mapping

### Before
```python
# services/device_specs.py - role mapping per manufacturer hardcoded
ROLE_MAPPING = {
    'shure': {
        'APPROVED': ['approved_1', 'approved_2'],
        'PENDING_APPROVAL': ['pending_1'],
    },
    'sennheiser': {
        'APPROVED': ['active', 'working'],
        'TESTING': ['test'],
    }
}

def get_roles_for_status(manufacturer, status):
    return ROLE_MAPPING.get(manufacturer.code, {}).get(status, [])
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry
import json

def get_roles_for_status(manufacturer, status):
    roles_json = SettingsRegistry.get(
        'device_roles_per_status',
        default='{}',
        manufacturer=manufacturer
    )
    mapping = json.loads(roles_json)
    return mapping.get(status, [])
```

## 7. Caching Strategies

### Before
```python
# Multiple modules with own caching logic
from functools import lru_cache

@lru_cache(maxsize=128)
def get_device_specs(manufacturer_code):
    # fetch from API or DB...
    return specs

# Problem: No cache invalidation strategy, memory waste
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry
from micboard.services.device_specs import DeviceSpecService

# Single unified caching approach
specs_cache_ttl = SettingsRegistry.get(
    'cache_device_specs_minutes',
    default=1440
)

# Service handles caching internally with TTL
specs = DeviceSpecService.get_specs(manufacturer)

# Invalidation happens automatically when settings update
```

## 8. Logging Configuration

### Before
```python
# polling_api.py - logging always on or off
import logging

logger = logging.getLogger(__name__)

class APIClient:
    def log_request(self, request):
        logger.debug(f"Request: {request}")  # Always logs based on logger level
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry
import logging

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, manufacturer, organization):
        self.manufacturer = manufacturer
        self.organization = organization

    def log_request(self, request):
        should_log = SettingsRegistry.get(
            'log_api_calls',
            default=False,
            organization=self.organization
        )
        if should_log:
            logger.info(f"API Request: {request}")
```

## 9. Feature Enablement

### Before
```python
# Scattered feature flags
ENABLE_DISCOVERY = True  # in settings.py
ENABLE_POLLING = True    # somewhere else
ENABLE_HEALTH_CHECK = False  # yet another place

# Usage requires multiple lookups
if ENABLE_DISCOVERY:
    service.discover()
```

### After
```python
from micboard.services.settings_registry import SettingsRegistry

# Single unified configuration
discovery_enabled = SettingsRegistry.get(
    'discovery_enabled',
    default=True,
    organization=organization
)
polling_enabled = SettingsRegistry.get(
    'polling_enabled',
    default=True,
    organization=organization
)

if discovery_enabled:
    service.discover()
```

## 10. Multi-Tenant Scope Usage

### Organization-Level Polling Interval

```python
# Each org can have different polling schedule
org1_interval = SettingsRegistry.get(
    'polling_interval_seconds',
    organization=org1  # Returns org1's setting only
)
org2_interval = SettingsRegistry.get(
    'polling_interval_seconds',
    organization=org2  # Returns org2's setting only
)
```

### Site-Specific API Timeouts

```python
# NYC site might need longer timeout (distance)
nyc_timeout = SettingsRegistry.get(
    'api_timeout',
    site=nyc_site,
    manufacturer=shure
)  # Returns site + mfg override, or org override, or global

# Local site can use shorter timeout
local_timeout = SettingsRegistry.get(
    'api_timeout',
    site=local_site,
    manufacturer=shure
)
```

### Manufacturer-Specific Device Limits

```python
# Shure might support 500 devices/call
shure_limit = SettingsRegistry.get(
    'device_max_requests_per_call',
    manufacturer=shure
)

# Sennheiser might only support 100
sennheiser_limit = SettingsRegistry.get(
    'device_max_requests_per_call',
    manufacturer=sennheiser
)
```

## 11. Migration Path

### Step 1: Add SettingDefinition
```bash
python manage.py init_settings
```

### Step 2: Update Code Service by Service
Start with non-critical services, gradually move to polling and discovery

### Step 3: Configure via Admin
```
1. Go to Django admin
2. Add Setting values (can start with defaults)
3. Test with warnings/logging
```

### Step 4: Deprecate Hardcoded Constants
Remove old CONFIG dictionaries as settings are verified working

### Step 5: Monitor Cache Behavior
Verify caching works as expected (5-min TTL)

## 12. Monitoring & Debugging

### Check Current Settings
```bash
python manage.py shell
from micboard.models.settings import Setting, SettingDefinition
Setting.objects.filter(definition__key='battery_low_level')
```

### Debug Scope Resolution
```python
from micboard.services.settings_registry import SettingsRegistry

# Check what value is being used
value = SettingsRegistry.get(
    'polling_interval_seconds',
    organization=org,
    site=site
)
print(f"Resolved to: {value}")

# Check cache status
SettingsRegistry.invalidate_cache('polling_interval_seconds')
```

### Verify Type Parsing
```python
from micboard.models.settings import SettingDefinition
defn = SettingDefinition.objects.get(key='polling_batch_size')
parsed = defn.parse_value('50')  # '50' -> 50
print(type(parsed))  # <class 'int'>
```

## 13. Performance Considerations

### Caching Reduces Queries
- Values cached for 5 minutes
- Definitions cached with LRU
- Each SettingsRegistry.get() is usually a cache hit

### Bulk Operations
```python
# Instead of multiple calls:
for setting_key in keys:
    value = SettingsRegistry.get(setting_key, organization=org)  # N queries

# Use bulk retrieval when possible:
all_settings = SettingsRegistry.get_all_for_scope(organization=org)
# Single query, returns dict of all scoped settings
```

### Cache Invalidation Strategy
```python
# Invalidate only what changed
SettingsRegistry.invalidate_cache('battery_low_level')  # Specific

# Or invalidate all after bulk update
SettingsRegistry.invalidate_cache()  # All settings
```

## Summary

The settings system provides:
- ✅ **Admin Configurability**: No code edits needed
- ✅ **Multi-Tenant Awareness**: Scope hierarchy for org/site/manufacturer
- ✅ **Type Safety**: Automatic parsing and validation
- ✅ **Performance**: Aggressive caching with TTL
- ✅ **Flexibility**: Easy to add new settings
- ✅ **Debugging**: Clear resolution and caching visibility
