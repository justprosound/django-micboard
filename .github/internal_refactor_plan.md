# Internal Refactor Plan (Phase 2)

## Overview Summary
- Goal: Realign django-micboard as a server-rendered Django app with HTMX-based interactivity, explicit services, and clean domains (hardware, location, rf, monitoring). Remove DRF entirely, avoid signals, and rely on services. Replace websocket broadcast UI paths with HTMX polling/partials. Add audit log archiving and dynamic logging verbosity to reduce churn.
- Scope: Greenfield models (no migrations generated), Django views + HTMX partials, services for all business logic, cleanup/renames, retention/archiving for audit/telemetry, kiosk/display walls via HTMX.
- Shure integration constraint: We do **not** talk to hardware directly; all Shure interactions occur via the Shure System API through service/middleware-style calls (no socket polling). Services must remain API-first and vendor-isolated.

## Gap Analysis vs Upstream micboard.io (code-only)
Feature | Upstream support | Our support | Notes
------- | ---------------- | ----------- | -----
Shure-only device polling (Tornado + JS) | Yes (Tornado server, JS HUD) | Yes (Django services; multi-vendor capable) | Keep multi-vendor; replace UI updates with HTMX.
Sennheiser/other vendors | No | Partial (integrations scaffolding) | Expand via manufacturer services; keep optional deps.
Device discovery (SLP/DCID) | Yes (py/discover.py) | Partial/Yes (discovery services/jobs) | Keep service-based discovery; no signals.
Live updates | Websocket push | Websocket broadcast present; HTMX not used | Move to HTMX polling/partials; gate websocket behind flag or remove.
Config/editor UI | JS drag/drop | Server templates only | Add HTMX fragments for assignments/groups; no SPA.
Performer/assignment model | No | Yes | Retain; HTMX CRUD.
Monitoring groups/location scoping | No | Yes | Keep; use in filters/services.
Regulatory/rf bands | No | Yes (rf_coordination models) | Keep and surface via rf service.
Charger dashboard / kiosk | Basic TV view | Yes (charger dashboard, display wall) | Convert updates to HTMX polling partials.
Audit/activity logging | No | Yes | Add archiving + verbosity modes.
Background tasks | No | Optional (django-q2) | Keep optional; invoke services.
DRF API | No | No (and must stay absent) | Ensure no DRF deps.

## New Domain Model Definitions (field-level; no code)
### hardware
- WirelessChassis: role (receiver/transmitter/transceiver); manufacturer/model/api_device_id/serial/mac; network (ip/subnet/gateway/mode + secondary NIC); status/is_online/last_seen/uptime; capabilities (max_channels, dante_capable, protocol_family, wmas_capable, licensed_resource_count); band plan (name/min/max MHz); location FK; rf_channels reverse; field_units reverse.
- RFChannel: chassis FK; channel_number; link_direction (receive/send/bidirectional); protocol_family; wmas_profile; licensed/enabled/resource_state; metrics RX (frequency, rf_signal_strength, audio_level, signal_quality, is_muted); metrics TX/IEM (iem_mix_level, iem_link_quality); active_wireless_unit FK (receive direction).
- WirelessUnit: device_type (mic_transmitter/iem_receiver/transceiver); base_chassis FK; assigned_resource FK to RFChannel; manufacturer/model/serial/slot/name; metrics TX (battery, battery_charge, battery_runtime, battery_type, audio_level, rf_level, quality, frequency, antenna, tx_offset); metrics IEM (iem_link_quality, iem_audio_level); status/api_status/is_muted/charging_status/last_seen/updated_at.
- Charger: location FK; manufacturer; model/serial/name/ip; status/is_active/firmware/last_seen/order/slot_count.
- ChargerSlot: charger FK; slot_number; occupied/is_functional; docked metadata (device_serial/device_model/battery_percent/device_firmware_version/device_status).
- DisplayWall: name, kiosk_id, is_active, location FK, layout metadata; WallSection reverse.
- WallSection: wall FK; display_order; is_active; chargers M2M; layout metadata.

### location
- Building: name/address/country/description; regulatory_domain FK; optional site FK (multi-site flag); auto-assign domain from country when missing.
- Room: building FK; name; floor; description; unique per building.
- Location: building FK; optional room FK; name/description; is_active; timestamps.

### rf
- RegulatoryDomain: code; country_code; name; min_frequency_mhz; max_frequency_mhz; description.
- FrequencyBand: regulatory_domain FK; name; start_frequency_mhz; end_frequency_mhz; band_type (allowed/restricted/forbidden); optional power_limit_mw/duty_cycle/channel_bandwidth_khz/licensing_info/fee_structure/description.
- ExclusionZone: name; optional regulatory_domain FK; latitude/longitude/radius_km; start_frequency_mhz/end_frequency_mhz; reason; is_active.

### monitoring
- MonitoringGroup: name/description/is_active/timestamps; users M2M; locations M2M via MonitoringGroupLocation; channels M2M.
- MonitoringGroupLocation: monitoring_group FK; location FK; include_all_rooms flag.
- Performer: name/title/role_description/photo/is_active/contact info/notes; timestamps.
- PerformerAssignment: performer FK; wireless_unit FK; monitoring_group FK; priority; notes; is_active; alert prefs (battery_low, signal_loss, audio_low, hardware_offline); audit fields (assigned_at/assigned_by/updated_at).
- Alert: links to performer_assignment and/or wireless_unit and/or user; type/status/message/snapshot; timestamps.
- RealTimeConnection: device/session health tracking (retain if needed by services only).

### telemetry/audit
- ActivityLog: actor/context/message/severity/object refs/timestamps.
- ServiceSyncLog: per sync run stats and errors.
- APIHealthLog: manufacturer API status history.
- Samples/Sessions: transmitter/wireless unit sample and session models (kept minimal; no migrations emitted).

## File/Folder Layout (target)
- micboard/models/
  - hardware/{chassis.py, unit.py, rf_channel.py, charger.py, display_wall.py}
  - location/{building.py, room.py, location.py}
  - rf/{regulatory_domain.py, frequency_band.py, exclusion_zone.py}
  - monitoring/{group.py, performer.py, assignment.py, alert.py, connection.py}
  - telemetry/{activity_log.py, api_health_log.py, samples.py, sessions.py, service_sync_log.py}
  - discovery/{job.py, queue.py, discovered_device.py, manufacturer_config.py}
  - users/{profile.py, view.py}
- micboard/services/
  - hardware.py, rf.py, location.py, monitoring.py, performer.py, performer_assignment.py, discovery.py, polling.py, manufacturer.py, kiosk.py, audit.py, logging_mode.py, utils.py
- micboard/views/
  - dashboard.py, alerts.py, assignments.py, kiosk.py, partials.py, locations.py
- micboard/templates/micboard/
  - base.html, index.html, alerts.html, assignments.html, kiosk/{display.html, wall_detail.html}, partials/{wall_section.html, channel_card.html, charger_slot.html, alert_row.html, assignment_row.html}

## UI Strategy (HTMX, no DRF)
- Keep server-rendered templates; add HTMX for partial refreshes (kiosk, chargers, assignments, alerts, device tiles).
- HTMX patterns: `hx-get` with `hx-trigger="load, every 2s"` (kiosk) or `every 5-10s` (dashboard); `hx-swap="outerHTML"/"innerHTML"`; scoped headers for wall/section IDs.
- Provide small JSON endpoints only when lighter than HTML; still served via Django views (no DRF).
- Remove websocket BroadcastService usage from UI; if kept for background integrations, gate behind a feature flag and keep disabled by default.

## Services Layer & Signals Strategy
- All business logic in services; models stay thin. No Django signals. Existing side-effects triggered explicitly (e.g., model save calls service helper) without registering signals.
- hardware service: device CRUD, capability sync, band plan detection, channel ensure, lifecycle transitions.
- rf service: regulatory checks, band coverage, exclusion handling, frequency utilities.
- location service: building/room/location CRUD, regulatory assignment.
- monitoring service: group scoping, channel access, alert evaluation entrypoints.
- performer/assignment services: CRUD, alert prefs, list helpers, assignment state transitions.
- discovery/polling/manufacturer services: orchestrate discovery queue, polling loops, vendor API normalization.
- kiosk service: compose wall/section/charger/channel data for HTMX fragments.
- audit service: logging writes, archiving, pruning.
- logging_mode service: manage verbosity state (passive/normal/high) with expiry; consulted by audit service.

## Audit Logging & Retention Strategy
- Add AuditService with functions to archive/prune ActivityLog, ServiceSyncLog, APIHealthLog using chunked deletes and optional export (CSV/Parquet to disk/S3). Retention configurable via MICBOARD_CONFIG; no migrations.
- Add LoggingMode controller (logging_mode.py): modes `passive` (critical only), `normal` (default), `high` (fine-grained). Store current mode + optional expiry (cache or small config table already present). Periodic task downgrades to normal after expiry.
- In high mode, direct verbose events to buffer/external sink when possible; summarize into ActivityLog to limit churn.
- Provide management commands/tasks: set logging mode with TTL; run archiver; run prune.

## Legacy/Stale Component Cleanup
- Remove DRF artifacts if any appear; ensure INSTALLED_APPS has no rest_framework; keep dependencies clean.
- Remove websocket/BroadcastService from UI pathways; optional flag if needed for integrations only.
- Remove signal emitter usages once HTMX is in place.
- Prune unused SPA/JS assets not referenced by templates.
- Consolidate templates under micboard/templates/micboard.

## Renaming Mapping (Old → New → Domain)
Old Path | New Path | Domain
--- | --- | ---
micboard/models/hardware/wireless_chassis.py | micboard/models/hardware/chassis.py | hardware
micboard/models/hardware/wireless_unit.py | micboard/models/hardware/unit.py | hardware
micboard/models/rf_coordination/rf_channel.py | micboard/models/hardware/rf_channel.py | hardware
micboard/models/monitoring/performer_assignment.py | micboard/models/monitoring/assignment.py | monitoring
micboard/services/broadcast_service.py (if present) | removed or gated (HTMX replaces) | ui
micboard/services/signal_emitter.py | removed after HTMX migration | ui
micboard/views/kiosk.py | micboard/views/kiosk.py + micboard/views/partials.py (HTMX) | ui
micboard/views/assignments.py | micboard/views/assignments.py (HTMX-enhanced) | monitoring

## Ordered Refactor Steps (Phase 3 instructions)
1) Create target folders/files per layout; add __init__.py as needed. Do not create migrations.
2) Move/implement models in new paths; update imports; keep Meta/indexes; ensure no signals.
3) Implement services: hardware, rf, location, monitoring, performer, assignment, discovery, polling, manufacturer, kiosk, audit, logging_mode; remove BroadcastService reliance from UI.
4) HTMX UI: add partial endpoints (partials.py) for kiosk walls/sections, charger grid, channel cards, alerts, assignments; wire templates with hx-get triggers.
5) Audit/Logging: add AuditService archiving/pruning and LoggingMode controls; add management commands/tasks to toggle mode and run archive; ensure ActivityLog writes respect mode.
6) Cleanup: remove websocket UI wiring, signal emitter usage, DRF remnants, unused SPA assets; keep optional deps behind flags.
7) Validation: run Django checks/lint; ensure imports resolve; verify no migrations produced. Tests unchanged in this phase.

## HTMX Endpoints Summary (targets)
- Dashboard index: HTMX fragments for device tiles/counters.
- Charger dashboard: grid fragment with periodic polling; POST for grid sizing.
- Assignments: list/table fragment; HTMX forms for create/update/delete.
- Alerts: list/row fragments; acknowledge/resolve via HTMX POST returning partial.
- Kiosk/display wall: wall/section fragments; channel/charger cards refreshed via hx-get with short intervals; optional JSON diff endpoints when smaller than HTML.

This plan is authoritative for Phase 3 implementation. Do not modify this file during Phase 3.
# Internal Refactor Plan - Standalone Django Micboard

## 1) Overview Summary


## 2) Gap Analysis vs Upstream micboard.io (Code-only)

| Feature | Upstream Support | Our Support | Notes |
|---|---|---|---|
| Shure devices (UHFR, QLXD, ULXD, Axient Digital, PSM1000) | Yes (py device drivers, Tornado server, JS UI) | Yes (integrations/shure with client, transformers, discovery, websocket) | Parity with richer services + Django models.
| Sennheiser devices | No clear upstream code for Sennheiser | Partial/Yes (integrations/sennheiser scaffolding) | Keep optional; expand via services.
| Device discovery (SLP/DCID) | Yes (py/discover.py) | Yes (services/discovery*, integrations/shure/discovery_*) | Align behind service API.
| Live data updates (WS/SSE) | Yes (Tornado WebSocket handlers) | Yes (integrations/shure/websocket.py, realtime models) | Keep optional; wrap in services.
| Grouped display boards | Yes (JS group editor, slots) | Yes (legacy `Group` model; dashboard views) | Maintain simple grouping for UI.
| Config editor (drag/drop) | Yes (front-end JS config) | Partial (server-side templates) | Plan HTMX-driven editor replacements.
| Regulatory compliance (domains/bands) | No | Yes (models/rf_coordination) | Retain and use in RF services.
| Multi-site / tenant awareness | No | Partial/Yes (settings/multitenancy, managers) | Keep optional flags; use managers/services.
| Monitoring teams/groups | No | Yes (`MonitoringGroup`, relations) | Central for access control and alerts.
| Performer + assignments | No | Yes (`Performer`, `PerformerAssignment`) | Core monitoring workflow.
| Telemetry sessions/samples | No | Yes (telemetry models) | Optional feature retained.
| Charger dashboard | No | Yes (`Charger`, `ChargerSlot`, view) | HTMX partials supported.
| Alerts (battery/signal/audio/offline) | No | Yes (views/alerts.py, services/email) | Consolidate logic in services.
| DRF API | No | Present (viewsets, serializers, permissions) | Must remove and replace with Django views.
| Rate limiting for endpoints | N/A | Present (decorators) | Adapt to Django views.
| Deduplication/manufacturer services | N/A | Present (services) | Keep; refactor under services.


## 3) New Domain Model Definitions (Field-level; no code)

### hardware
  - Role: `receiver | transmitter | transceiver`
  - Identity: `manufacturer`, `model`, `api_device_id`, `serial_number`, `mac_address`
  - Network: `ip`, `subnet_mask`, `gateway`, `network_mode`, optional secondary NIC
  - Status: `status`, `is_online`, `last_seen`, uptime tracking
  - Capabilities: `max_channels`, `dante_capable`, `protocol_family`, `wmas_capable`, `licensed_resource_count`
  - Band plan: `band_plan_name`, `band_plan_min_mhz`, `band_plan_max_mhz`
  - Relations: `location (FK)`, `rf_channels (reverse)`, `field_units (reverse)`

  - Type: `mic_transmitter | iem_receiver | transceiver`
  - Relations: `base_chassis (FK)`, optional `assigned_resource (FK to RFChannel)`
  - Identity: `manufacturer`, `model`, `serial_number`, `slot`, `name`
  - Metrics (TX): `battery`, `battery_charge`, `battery_runtime`, `battery_type`, `audio_level`, `rf_level`, `quality`, `frequency`, `antenna`, `tx_offset`
  - Metrics (IEM): `iem_link_quality`, `iem_audio_level`
  - Status: `status`, `api_status`, `is_muted`, `charging_status`, `last_seen`, `updated_at`

  - Relations: `location (FK)`, `manufacturer`
  - Identity: `model`, `serial_number`, `name`, `ip`
  - Status: `is_active`, `status`, `firmware_version`, `last_seen`, `order`, `slot_count`

  - Relations: `charger (FK)`
  - Slot: `slot_number`, `occupied`, `is_functional`
  - Docked metadata: `device_serial`, `device_model`, `battery_percent`, `device_firmware_version`, `device_status`

### location

### rf
  - Relations: `chassis (FK)`, optional `active_wireless_unit (FK)`, optional `active_iem_receiver (FK)`
  - Topology: `channel_number`, `link_direction (receive|send|bidirectional)`
  - Protocol: `protocol_family`, `wmas_profile`, `licensed`, `enabled`, `resource_state`
  - Metrics (RX): `frequency`, `rf_signal_strength`, `audio_level`, `signal_quality`, `is_muted`
  - Metrics (IEM): `iem_mix_level`, `iem_link_quality`


### monitoring

### File/Folder Layout (authoritative)

```
models/hardware/
models/location/
models/rf/
models/monitoring/
services/
```


## 4) UI Strategy (HTMX, No DRF)
  - List/detail views return HTML; HTMX requests return partial fragments.
  - Minimal machine-readable JSON responses (e.g., POST actions, small polling endpoints) returned via `JsonResponse`.
  - Devices: chassis/unit lists, filtered by manufacturer/location/group.
  - Assignments: create/update/delete via HTMX forms; partials update relevant sections.
  - Alerts: acknowledge/resolve via POST; partial counters/rows update.
  - Charger dashboard: HTMX fragment for grid; size/width updates via POST JSON.


## 5) Services Layer & Signals Strategy
  - `services/device.py`: device CRUD, capability sync, band plan detection, channel ensure, lifecycle transitions.
  - `services/location.py`: building/room/location CRUD, regulatory domain application.
  - `services/rf.py`: RF coordination, regulatory checks, frequency planning helpers.
  - `services/monitoring_service.py`: monitoring group/user access, filtering helpers.
  - `services/performer.py`, `services/performer_assignment.py`: assignment lifecycle, alert prefs, lookups.
  - `services/alerts.py`: alert evaluation/creation/email dispatch; callable from views/services.
  - `services/connection.py`: `RealTimeConnection` health/heartbeat, unhealthy list.
  - `services/discovery.py`: orchestrate discovery/sync; manufacturer integrations.
  - `services/manufacturer_service.py`: uniform interface for vendor APIs.
  - `services/device_sync_service.py`: consolidate sync side-effects previously in signals.
  - Delete device-related signals; move side-effects to explicit service calls (e.g., call `DeviceService.handle_chassis_save` from model `save()` or from views/commands).
  - Delete `user_signals` (profile last_login update) and replace with middleware-based or service-invoked update during authenticated requests (e.g., lightweight `UserActivityMiddleware` that updates `UserProfile.last_login` once per session boundary).
  - Keep no signals unless a behavior is technically impossible elsewhere (none identified).


## 6) Legacy/Stale Component Cleanup
  - Remove `micboard/viewsets.py`.
  - Remove `micboard/serializers/` (all DRF serializers).
  - Remove `micboard/permissions/permissions.py` (DRF imports).
  - Delete `micboard/signals/device_signals.py`.
  - Delete `micboard/signals/user_signals.py` (replace with middleware approach).
  - Minimize `micboard/signals/__init__.py` or remove if unused.
  - Drop `djangorestframework` from dependencies and any DRF stubs or configs.


## 7) Renaming Mapping Table (Old → New → Domain)

| Old Path | New Path | Domain |
|---|---|---|
| micboard/models/hardware/wireless_chassis.py | models/hardware/wireless_chassis.py | hardware |
| micboard/models/hardware/wireless_unit.py | models/hardware/wireless_unit.py | hardware |
| micboard/models/hardware/charger.py | models/hardware/charger.py | hardware |
| micboard/models/locations/structure.py | models/location/structure.py | location |
| micboard/models/rf_coordination/rf_channel.py | models/rf/rf_channel.py | rf |
| micboard/models/rf_coordination/compliance.py | models/rf/compliance.py | rf |
| micboard/models/monitoring/group.py | models/monitoring/group.py | monitoring |
| micboard/models/monitoring/performer.py | models/monitoring/performer.py | monitoring |
| micboard/models/monitoring/performer_assignment.py | models/monitoring/performer_assignment.py | monitoring |
| micboard/models/realtime/connection.py | models/monitoring/connection.py | monitoring |
| micboard/models/telemetry/sessions.py | models/monitoring/telemetry.py | monitoring |
| micboard/viewsets.py | (delete) | N/A |
| micboard/serializers/* | (delete) | N/A |
| micboard/permissions/permissions.py | (delete) | N/A |
| micboard/signals/* | (delete) | N/A |

Notes:


## 8) Ordered Refactor Steps (Phase 3 Instructions)
1. Create new domain folders and placeholder `__init__.py` under `models/hardware`, `models/location`, `models/rf`, `models/monitoring`.
2. Move/implement greenfield models in the new paths per section (3); do not generate migrations.
3. Implement `services/` modules and consolidate business logic (device sync, RF coordination, monitoring, alerts, discovery, connection health).
4. Replace DRF endpoints:
   - Remove `micboard/viewsets.py`, serializers, permissions.
   - Implement Django views for device lists/detail, assignments CRUD, alerts actions, connection health, and charger dashboard. Return HTML; support HTMX via partial templates and `HX-Request` checks; return JSON only where strictly useful.
5. Update `INSTALLED_APPS` and dependencies:
   - Remove DRF from installed apps and `pyproject.toml` dependencies.
   - Keep optional `channels`, `django-q`, `websockets`, `prometheus-client` off by default; code degrades gracefully if not installed.
6. Remove signals:
   - Delete device/user signal modules; remove remaining `signals/__init__.py` if no references.
   - Add simple middleware (`UserActivityMiddleware`) to update `UserProfile.last_login` for authenticated users once per session window.
7. Update imports in existing views/commands/templates to the new model/service paths.
8. Implement HTMX partials for charger dashboard and any list fragments (e.g., assignments list, alerts tables). Ensure views handle `HX-Request` header for partial template selection.
9. Run `django check` and linting to ensure syntax/consistency (no migrations). Validate without touching tests yet.
10. Remove dead code and files identified in cleanup; ensure repo consistency.


## 9) HTMX Endpoints Summary (Implementation Targets)

This plan is authoritative for Phase 3 implementation. Do not modify this file during Phase 3.
