"""Django Micboard - Architecture & Developer Guide

## Core Architecture

Django Micboard is a reusable Django app for monitoring multi-manufacturer
wireless audio hardware. It emphasizes:

- **DRY Code**: Reduced duplication through registries and base classes
- **Manufacturer-Agnostic Core**: Plugin architecture for manufacturer-specific logic
- **Multi-Tenant Safe**: Site/Organization/Campus scoping with settings inheritance
- **Settings Registry**: Centralized typed config at each definition's exact declared scope

## Key Components

### 1. Settings & Configuration

The settings service provides the single access point for all Micboard settings:

```python
from micboard.services.settings.settings_service import settings as micboard_settings

# Feature flags
if micboard_settings.msp_enabled:
    print("MSP mode is enabled")

# Settings from MICBOARD_CONFIG dict
timeout = micboard_settings.get("SHURE_API_TIMEOUT", default=10)

# Direct property access
allowed = micboard_settings.allow_cross_org_view
```

**Resolution Order** (`services/settings/settings_service.py`):
1. Immutable Django host setting for `MICBOARD_*` deployment controls
2. Scoped database setting (organization, site, or manufacturer)
3. Host `MICBOARD_CONFIG` dictionary
4. App default
5. Registered definition default
6. Caller-provided default

### 2. Plugin Architecture (Manufacturer-Agnostic)

Manufacturer-specific protocol logic lives in `micboard/integrations/<manufacturer>/`. Shared
transport, response bounds, retries, rate limiting, health behavior, and plugin contracts live in
`micboard/services/common/base/`; the common exception hierarchy lives in
`micboard/exceptions.py`.

```
micboard/
  exceptions.py
  services/
    common/base/
      plugin.py           # ManufacturerPlugin and convention-based class discovery
      client.py           # Verified HTTP transport
      bounded_transport.py
      rate_limiter.py
    manufacturer/
      plugin_registry.py  # Cached class lookup and instance construction
  integrations/
    shure/                 # REST, discovery, transforms, WebSocket
    sennheiser/            # REST, discovery, transforms, SSE
```

**Using the Plugin Registry:**

```python
from micboard.services.manufacturer.plugin_registry import PluginRegistry

# Get plugin class
plugin_class = PluginRegistry.get_plugin_class("shure")

# Get plugin instance
plugin = PluginRegistry.get_plugin("shure", manufacturer=shure_obj)

# Get all active plugins
plugins = PluginRegistry.get_all_active_plugins()
```

**Implementing a New Plugin:** Create `micboard/integrations/<code>/plugin.py` with a concrete,
conventionally named `ManufacturerPlugin` subclass. For code `my_manufacturer`, the loader prefers
`MyManufacturerPlugin`. Create a matching active `Manufacturer` row, then verify discovery with
`PluginRegistry.get_plugin_class("my_manufacturer")`. There is no central registration map or
package re-export to edit. See [Manufacturer plugin development](../docs/plugin-development.md) for
the complete contract.

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

### 4. Scoped Settings

Add custom app settings with scope-aware resolution:

```python
from micboard.services.settings.settings_service import settings as micboard_settings

# Resolve at the setting definition's declared scope
value = micboard_settings.get(
    'CUSTOM_KEY',
    organization=org,
    site=site,
    manufacturer=manufacturer,
    default='fallback',
)

# Deployment controls are host-owned and cannot be overridden by database rows.
limit = micboard_settings.get('MICBOARD_REALTIME_MAX_DEVICES', 128)
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

- `manufacturer/plugin_registry.py`: Manufacturer plugin loading
- `settings/settings_service.py`: Unified host and scoped settings resolution
- `settings/registry.py`: Internal database-backed scope resolution
- `settings/persistence_service.py`: Authorized scoped setting writes
- `hardware/wireless_chassis_persistence_service.py`: Typed chassis create/update/upsert boundary
- `hardware/chassis_lifecycle_service.py`: Chassis save transitions and committed side effects
- `hardware/chassis_regulatory_service.py`: Band-plan detection, enrichment, and coverage
- `core/hardware.py`: Hardware query and synchronization facade
- `core/hardware_sync.py`: Hardware status and channel synchronization
- `sync/polling_api.py`: Direct API polling
- `sync/discovery_service.py`: Device discovery
- `monitoring/alerts.py`: Alert management
- `core/performer_assignment.py`: Performer assignment

## Testing

Run the full test suite:

```bash
uv run --no-sync pytest  # All tests
uv run --no-sync pytest tests/test_chargers.py  # Specific test file
uv run --no-sync pytest -m unit  # Unit tests only
uv run --no-sync pytest -m integration  # Integration tests
uv run --no-sync pytest --cov=micboard  # With coverage
```

**Test markers** (see pyproject.toml):
- `unit`: Fast, isolated tests
- `integration`: Slower, external dependencies
- `e2e`: Full workflow tests
- `slow`: Long-running tests
- `plugin`: Plugin-specific tests
- `django_db`: Requires database

## Best Practices for Contributors

1. **Always use `SettingsService`** for settings reads and the persistence service for writes
2. **Extend base classes** for models, views, services
3. **Add type hints** for all public functions
4. **Document scope requirements** (tenant, site, org)
5. **Test multi-tenant behavior** in integration tests
6. **Avoid hard-coded manufacturer names** – use plugins
7. **Don't modify migrations** – create new ones only if schema changes

## Release Checklist

- [ ] All tests pass: `uv run --no-sync pytest --cov=micboard --cov-branch --cov-fail-under=95`
- [ ] Ruff checks: `uv run --no-sync ruff check .`
- [ ] Pre-commit hooks: `uv run --no-sync pre-commit run --all-files`
- [ ] No tracked dev artifacts (db.sqlite3, .env, egg-info)
- [ ] CHANGELOG.md updated
- [ ] Version number updated in `pyproject.toml` (`micboard.__version__` reads package metadata)

## Further Reading

- [Settings System](../SETTINGS_MANAGEMENT.md)
- [Plugin System](../docs/plugin-development.md)
- [Models](models/)
- [Contributing](../CONTRIBUTING.md)
- [Tests](../tests/)
