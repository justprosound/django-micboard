---
title: "Architecture"
description: "How django-micboard is structured: settings, plugins, tenancy, models, services and runtime processes."
type: explanation
audience: developer
---
## Core Architecture

Django Micboard is a reusable Django app for monitoring multi-manufacturer wireless audio hardware. It emphasizes:

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
max_devices = micboard_settings.get("MICBOARD_REALTIME_MAX_DEVICES", 128)

# Direct property access
allowed = micboard_settings.allow_cross_org_view
```

Resolution order is described in [Settings management](guides/settings-management.md).

### 2. Plugin Architecture (Manufacturer-Agnostic)

Manufacturer-specific protocol logic lives in `micboard/integrations/<manufacturer>/`. Shared transport, response bounds, retries, rate limiting, health behavior, and plugin contracts live in `micboard/services/common/base/`; the common exception hierarchy lives in `micboard/exceptions.py`.

```
micboard/
  exceptions.py
  services/
    common/base/
      plugin.py           # ManufacturerPlugin, cached class discovery, bound construction
      client.py           # Verified HTTP transport
      bounded_transport.py
      rate_limiter.py
  integrations/
    shure/                 # REST, discovery, transforms, WebSocket
    sennheiser/            # REST, discovery, transforms, SSE
```

**Obtaining a plugin:**

```python
from micboard.services.common.base.plugin import (
    build_manufacturer_plugin,
    get_manufacturer_plugin,
)

# Resolve the plugin class for a manufacturer code (cached per process)
plugin_class = get_manufacturer_plugin("shure")

# Build a plugin bound to a persisted manufacturer — the one way callers get an instance
plugin = build_manufacturer_plugin(shure_obj)
```

`build_manufacturer_plugin` raises `ModuleNotFoundError` or `ImportError` when a manufacturer
has no shipped integration, so every outbound path sees the same failure instead of a `None`
some callers branch on and others do not.

**Implementing a New Plugin:** Create `micboard/integrations/<code>/plugin.py` with a concrete, conventionally named `ManufacturerPlugin` subclass. For code `my_manufacturer`, the loader prefers `MyManufacturerPlugin`. Create a matching active `Manufacturer` row, then verify discovery with `get_manufacturer_plugin("my_manufacturer")`. There is no central registration map or package re-export to edit. See [Manufacturer plugin development](plugin-development.md) for the complete contract.

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
from micboard.services.shared.visibility import visible_to
# Scope querysets explicitly to the authenticated user.
devices = visible_to(WirelessUnit, user=request.user)
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

- `common/base/plugin.py`: Manufacturer plugin resolution and construction
- `settings/settings_service.py`: Unified host and scoped settings resolution
- `settings/registry.py`: Internal database-backed scope resolution
- `settings/persistence_service.py`: Authorized scoped setting writes
- `hardware/wireless_chassis_persistence_service.py`: Typed chassis create/update/upsert boundary
- `hardware/chassis_lifecycle_service.py`: Chassis save transitions and committed side effects
- `hardware/chassis_regulatory_service.py`: Band-plan detection, enrichment, and coverage
- `core/hardware.py`: Hardware query and synchronization facade
- `core/hardware_sync.py`: RF channel synchronization
- `sync/polling_api.py`: Direct API polling
- `sync/discovery_service.py`: Device discovery
- `monitoring/alerts.py`: Alert management
- `core/performer_assignment.py`: Performer assignment

## Runtime processes and real-time state

A production deployment runs these cooperating processes:

- the Django web application, plus an ASGI server if WebSocket push is enabled ([Set up real-time updates](guides/realtime-updates.md));
- a native Huey consumer for queued polls;
- a scheduler that invokes `poll_devices --async` at the interval you choose, because polling never starts subscription supervisors;
- one `realtime_subscribe` supervisor per manufacturer, when streaming is wanted;
- a shared cache and channel layer (for example Redis) so leases and fan-out work across processes, and a database.

Each streaming session is tracked in a `RealTimeConnection` row (`micboard/models/realtime/connection.py`) with a status of `connecting`, `connected`, `disconnected`, `error` or `stopped`. `realtime_status` and the admin read those rows.

Browser pages poll over HTTP by default and the WebSocket consumer broadcasts `device_update`, `device_status_update` and `api_health_update` events to authenticated clients ([WebSocket API](api/websocket.md)).

## Further Reading

- [Settings management](guides/settings-management.md)
- [Manufacturer plugin development](plugin-development.md)
- [Developer guide](development.md)
- [Architecture decisions](adr/002-extract-model-business-logic.md)
