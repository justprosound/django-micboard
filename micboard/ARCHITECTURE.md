"""Django Micboard - Architecture & Developer Guide

## Core Architecture

Django Micboard is a reusable Django app for monitoring multi-manufacturer
wireless audio hardware. It emphasizes:

- **DRY Code**: Reduced duplication through registries and base classes
- **Manufacturer-Agnostic Core**: Plugin architecture for manufacturer-specific logic
- **Multi-Tenant Safe**: Site/Organization/Campus scoping with settings inheritance
- **Settings Registry**: Centralized config with scope-aware fallback (global → site → org)

## Key Components

### 1. Settings & Configuration

The settings service provides the single access point for all Micboard settings:

```python
from micboard.services.settings import settings as micboard_settings

# Feature flags
if micboard_settings.msp_enabled:
    print("MSP mode is enabled")

# Settings from MICBOARD_CONFIG dict
timeout = micboard_settings.get("SHURE_API_TIMEOUT", default=10)

# Direct property access
allowed = micboard_settings.allow_cross_org_view
```

**Resolution Order** (`services/settings/settings_service.py`):
1. Scoped database setting (organization, site, or manufacturer)
2. Host `MICBOARD_CONFIG` dictionary
3. Host feature-flag setting
4. App default
5. Caller-provided default

### 2. Plugin Architecture (Manufacturer-Agnostic)

Manufacturer-specific logic lives in `micboard/integrations/<manufacturer>/`, inheriting from shared base classes in `micboard/integrations/common/`:

```
micboard/integrations/
  common/
    __init__.py           # Plugin loader, shared exports
    base.py               # ManufacturerPlugin, BasePlugin, BaseAPIClient
    exceptions.py         # Shared exception taxonomy
    rate_limiter.py       # Shared rate-limiting logic
  shure/
    __init__.py
    plugin.py             # ShurePlugin implementation
    client.py             # Shure HTTP client
    websocket.py          # Real-time telemetry
  sennheiser/
    __init__.py
    plugin.py             # SennheiserPlugin implementation
    client.py             # Sennheiser HTTP client
```

**Using the Plugin Registry:**

```python
from micboard.services.manufacturer.plugin_registry import PluginRegistry

# Get plugin class
plugin_class = PluginRegistry.get_plugin_class('shure')

# Get plugin instance
plugin = PluginRegistry.get_plugin('shure', manufacturer=shure_obj)

# Get all active plugins
plugins = PluginRegistry.get_all_active_plugins()
```

**Implementing a New Plugin:**

```python
from micboard.services.common.base.plugin import ManufacturerPlugin

class MyPlugin(ManufacturerPlugin):
    manufacturer_code = 'mymanufacturer'

    def get_devices(self) -> list:
        # Fetch devices from API
        pass

    def poll_device(self, device_id: str) -> dict:
        # Poll telemetry for a device
        pass

# Register in micboard/integrations/common/__init__.py
def get_manufacturer_plugin(code: str):
    if code == 'mymanufacturer':
        return MyPlugin
    raise ModuleNotFoundError(f"No plugin for {code}")
```

### 3. Multi-Tenancy

Configure multi-tenancy in your Django settings:

```python
# Minimal (single-site)
MICBOARD_MULTI_SITE_MODE = False
MICBOARD_MSP_ENABLED = False

# Multi-site enterprise
MICBOARD_MULTI_SITE_MODE = True
MICBOARD_SITE_ISOLATION = 'site'

# Full MSP
MICBOARD_MULTI_SITE_MODE = True
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'organization'
```

**Scoping Queries:**

```python
# Scope querysets explicitly to the authenticated user.
devices = WirelessUnit.objects.for_user(user=request.user)
```

### 4. Settings Registry

Add custom app settings with scope-aware resolution:

```python
from micboard.services.shared.settings_registry import SettingsRegistry

# Get with scope hierarchy
value = SettingsRegistry.get(
    'CUSTOM_KEY',
    organization=org,
    site=site,
    manufacturer=manufacturer,
    default='fallback'
)

# Required settings raise error if not found
value = SettingsRegistry.get(
    'REQUIRED_KEY',
    required=True
)
```

## Models & Domains

Models are organized by business domain in `micboard/models/`:

```
micboard/models/
  __init__.py           # All exports
  audit/                # Activity logs, audit trails
  discovery/            # Device discovery, manufacturers
  hardware/             # Wireless units, chassis, chargers
  integrations/         # Third-party integrations
  locations/            # Buildings, rooms, zones
  monitoring/           # Alerts, performers, assignments
  realtime/             # WebSocket connections
  rf_coordination/      # Frequency bands, channels
  telemetry/            # Samples, sessions, health
  users/                # User profiles, permissions
```

## Services & Business Logic

Core services in `micboard/services/`:

- `plugin_registry.py`: Manufacturer plugin loading
- `settings_registry.py`: Scope-aware settings resolution
- `manufacturer_config_registry.py`: Per-manufacturer configs
- `hardware.py`: Hardware query and lifecycle
- `hardware_sync_service.py`: API polling and sync
- `polling_api.py`: Direct API polling
- `discovery_service_new.py`: Device discovery
- `alert.py`: Alert management
- `performer.py`: Performer assignment

## Testing

Run the full test suite:

```bash
pytest              # All tests
pytest tests/test_chargers.py  # Specific test file
pytest -m unit      # Unit tests only
pytest -m integration  # Integration tests
pytest --cov=micboard  # With coverage
```

**Test markers** (see pyproject.toml):
- `unit`: Fast, isolated tests
- `integration`: Slower, external dependencies
- `e2e`: Full workflow tests
- `slow`: Long-running tests
- `plugin`: Plugin-specific tests
- `django_db`: Requires database

## Best Practices for Contributors

1. **Always use the registry pattern** for settings/config
2. **Extend base classes** for models, views, services
3. **Add type hints** for all public functions
4. **Document scope requirements** (tenant, site, org)
5. **Test multi-tenant behavior** in integration tests
6. **Avoid hard-coded manufacturer names** – use plugins
7. **Don't modify migrations** – create new ones only if schema changes

## Release Checklist

- [ ] All tests pass: `pytest --cov=micboard --cov-fail-under=85`
- [ ] Ruff checks: `ruff check .`
- [ ] Pre-commit hooks: `pre-commit run --all-files`
- [ ] No tracked dev artifacts (db.sqlite3, .env, egg-info)
- [ ] CHANGELOG.md updated
- [ ] Version number updated (pyproject.toml, __init__.py)

## Further Reading

- [Settings System](micboard/settings/multitenancy.py)
- [Plugin System](micboard/integrations/common/base.py)
- [Models](micboard/models/)
- [Contributing](CONTRIBUTING.md)
- [Tests](tests/)
"""
