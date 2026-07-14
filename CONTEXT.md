# django-micboard - Domain Context

## Purpose

django-micboard is a Django-based wireless microphone fleet management system. It discovers, monitors, and manages RF (radio frequency) devices across venues - tracking chassis, wireless units, chargers, frequencies, performers, and compliance with regional RF regulations.

## Core Domain Concepts

### Hardware Inventory

- **WirelessChassis** - A physical receiver/transmitter/transceiver unit (e.g., Shure ULX-D rack). Has a manufacturer, model, IP address, firmware version, band plan, and slot capacity. Each chassis hosts one or more RF channels.
- **WirelessUnit** - An individual wireless device (mic transmitter, IEM receiver, or transceiver) associated with a chassis slot. Tracks battery level, audio level, RF level, signal quality, and connection status.
- **RFChannel** - A logical channel within a chassis representing a frequency slot. Links chassis to wireless units, tracks link direction (transmit/receive), signal metrics, and resource state.
- **Charger / ChargerSlot** - Multi-bay charging stations. Each slot can hold a device and optionally be assigned to a performer.
- **DisplayWall / WallSection** - Kiosk displays showing charger/performer status on wall-mounted screens.

### Discovery & Sync

- **Manufacturer** - A supported hardware vendor (Shure, Sennheiser, Wisycom, etc.). Each has a plugin implementation.
- **DiscoveryCIDR / DiscoveryFQDN** - Network ranges and hosts where the system scans for devices.
- **DiscoveredDevice** - A device found during network discovery but not yet adopted.
- **DiscoveryQueue** - Pending adoption items: devices found during discovery awaiting user review.
- **DiscoveryJob** - Tracks a scan run: manufacturer, action, status, item counts.
- **DeviceMovementLog** - Records when a device's IP or location changes.

### Monitoring & Alerts

- **Performer** - A person using a wireless microphone/IEM system.
- **PerformerAssignment** - Links a performer to a wireless unit and a monitoring group.
- **MonitoringGroup** - A named group with assigned users, locations, and channels for monitoring.
- **Alert** - A triggered notification for battery low, signal loss, or hardware offline conditions.
- **UserAlertPreference** - Per-user alert routing (email, push) and quiet-hour config.

### RF Coordination

- **RegulatoryDomain** - A country/region's RF regulatory body (FCC, ETSI, etc.).
- **FrequencyBand** - A frequency range within a regulatory domain with power limits.
- **ExclusionZone** - Geographic areas where certain frequencies are prohibited.

### Settings & Configuration

- **SettingDefinition** - Schema for a configurable setting (key, label, type, scope, default).
- **Setting** - A scoped setting value (global -> site -> organization -> manufacturer).
- **ManufacturerConfiguration** - JSON-based manufacturer-specific configuration with validation.
- **SettingsService** - Runtime settings service merging host settings, feature flags, app
  defaults, and scoped database configuration.

### Multi-Tenancy

- **Organization** - Top-level tenant. Has subscription tier, device limits, primary contact.
- **Campus** - Sub-tenant within an organization.
- **OrganizationMembership** - User-organization binding with role and campus scope.

### Audit & Telemetry

- **ActivityLog** - Generic audit trail for all model operations.
- **ConfigurationAuditLog** - Tracks manufacturer config changes.
- **ServiceSyncLog** - Tracks sync runs per manufacturer service.
- **APIHealthLog** - Response-time and status tracking for manufacturer API endpoints.
- **WirelessUnitSession / WirelessUnitSample** - Time-series telemetry for unit metrics.

## Architecture Patterns

- **Django Admin as UI** - The primary user interface is Django's admin, heavily customized with HTMX views. No REST API layer exists.
- **Service Layer** - Business logic lives in `micboard/services/<domain>/services.py`. Services orchestrate models, plugins, and external APIs.
- **Plugin System** - Manufacturer integrations live in `micboard/integrations/<manufacturer>/` with a `plugin.py`, `client.py`, `discovery_client.py`, `transformers.py`, and optional `websocket.py`/`sse_client.py`.
- **Background Tasks** - Discovery, polling, health checks, and WebSocket subscriptions run via native Huey tasks in `micboard/tasks/<domain>/`.
- **Async Real-Time** - Server-sent events (SSE) and WebSocket connections for live monitoring.
- **Multi-Tenancy** - Row-level tenant isolation via `TenantOptimizedQuerySet` / `TenantOptimizedManager`.
- **Settings Resolution** - Scoped settings cascade: global -> site -> organization -> manufacturer.
- **Self-Contained Verification** - CI enforces coverage locally and publishes HTML/XML artifacts.
  External reporting services are optional and must not become required until the repository is
  explicitly onboarded.

## Known Architectural Debt

1. ~~**Service layer monoliths** - Oversized discovery and lifecycle services were split into
   domain-focused modules.~~
2. **Model embedded logic** - `WirelessChassis.save()`, `ManufacturerConfiguration.validate()` contain business logic that belongs in services.
3. ~~**Admin dashboard monolith** - The former dashboard module was split into focused admin and
   view modules.~~
4. **Manufacturer plugin duplication** - Shure + Sennheiser plugin stacks are 80-90% structurally identical; no shared base reduces maintenance.
5. ~~**Thin test coverage** - Branch coverage now exceeds 95%, with model factories plus service,
   integration, command, admin, and host-configuration contracts enforced in CI.~~
6. ~~**Compat shim** - `micboard/manufacturers/` was a backward-compat shim. Now removed (ADR-008).~~

## Key File Locations

| Concern | Path |
|---|---|
| Models | `micboard/models/<domain>/` |
| Services | `micboard/services/<domain>/` |
| Admin views | `micboard/admin/` |
| Tasks (Huey) | `micboard/tasks/<domain>/` |
| Manufacturer plugins | `micboard/integrations/<manufacturer>/` |
| View layer (non-admin) | `micboard/views/` |
| Settings service | `micboard/services/settings/settings_service.py` |
| DB settings models | `micboard/models/settings/registry.py` |
| Scoped settings backend | `micboard/services/shared/settings_registry.py` |
| ~~Legacy compat shim~~ | ~~`micboard/manufacturers/`~~ (removed) |
| Tests | `tests/` (flat) |
| Fixtures | `micboard/fixtures/` |
| Huey integration | `huey.contrib.djhuey` plus the project's `HUEY` setting |
| URLs | `micboard/urls.py`, `micboard/urls/` |
| Middleware | `micboard/multitenancy/middleware.py` |
| Metrics | `micboard/metrics.py` |
| Exceptions | `micboard/exceptions.py` |
