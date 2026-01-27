# Internal Refactor Plan - Standalone Django Micboard

## 1) Overview Summary
- Goal: Realign django-micboard into a full-featured standalone Django application using server-rendered templates with HTMX, explicit services layer, and clean domain models for hardware, location, RF, and monitoring. Remove DRF entirely and minimize signals.
- Scope: Greenfield database modeling (no legacy migrations), replace DRF endpoints with Django views/HTMX, consolidate domain logic in services, and prune/rename legacy/stale components.

---

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

---

## 3) New Domain Model Definitions (Field-level; no code)

### hardware
- `WirelessChassis`
  - Role: `receiver | transmitter | transceiver`
  - Identity: `manufacturer`, `model`, `api_device_id`, `serial_number`, `mac_address`
  - Network: `ip`, `subnet_mask`, `gateway`, `network_mode`, optional secondary NIC
  - Status: `status`, `is_online`, `last_seen`, uptime tracking
  - Capabilities: `max_channels`, `dante_capable`, `protocol_family`, `wmas_capable`, `licensed_resource_count`
  - Band plan: `band_plan_name`, `band_plan_min_mhz`, `band_plan_max_mhz`
  - Relations: `location (FK)`, `rf_channels (reverse)`, `field_units (reverse)`

- `WirelessUnit`
  - Type: `mic_transmitter | iem_receiver | transceiver`
  - Relations: `base_chassis (FK)`, optional `assigned_resource (FK to RFChannel)`
  - Identity: `manufacturer`, `model`, `serial_number`, `slot`, `name`
  - Metrics (TX): `battery`, `battery_charge`, `battery_runtime`, `battery_type`, `audio_level`, `rf_level`, `quality`, `frequency`, `antenna`, `tx_offset`
  - Metrics (IEM): `iem_link_quality`, `iem_audio_level`
  - Status: `status`, `api_status`, `is_muted`, `charging_status`, `last_seen`, `updated_at`

- `Charger`
  - Relations: `location (FK)`, `manufacturer`
  - Identity: `model`, `serial_number`, `name`, `ip`
  - Status: `is_active`, `status`, `firmware_version`, `last_seen`, `order`, `slot_count`

- `ChargerSlot`
  - Relations: `charger (FK)`
  - Slot: `slot_number`, `occupied`, `is_functional`
  - Docked metadata: `device_serial`, `device_model`, `battery_percent`, `device_firmware_version`, `device_status`

### location
- `Building`: `name`, `address`, `country`, `description`, optional `site (FK)`, `regulatory_domain (FK)`
- `Room`: `building (FK)`, `name`, `floor`, `description`
- `Location`: `building (FK)`, optional `room (FK)`, `name`, `description`, `is_active`, timestamps

### rf
- `RFChannel`
  - Relations: `chassis (FK)`, optional `active_wireless_unit (FK)`, optional `active_iem_receiver (FK)`
  - Topology: `channel_number`, `link_direction (receive|send|bidirectional)`
  - Protocol: `protocol_family`, `wmas_profile`, `licensed`, `enabled`, `resource_state`
  - Metrics (RX): `frequency`, `rf_signal_strength`, `audio_level`, `signal_quality`, `is_muted`
  - Metrics (IEM): `iem_mix_level`, `iem_link_quality`

- `RegulatoryDomain`: `code`, `country_code`, `name`, `min_frequency_mhz`, `max_frequency_mhz`, `description`
- `FrequencyBand`: `regulatory_domain (FK)`, `name`, `start_frequency_mhz`, `end_frequency_mhz`, `band_type`, optional: `power_limit_mw`, `duty_cycle`, `channel_bandwidth_khz`, `licensing_info`, `fee_structure`, `description`
- `ExclusionZone`: `name`, optional `regulatory_domain (FK)`, geo (`latitude`, `longitude`, `radius_km`), exclusion freq range (`start_frequency_mhz`, `end_frequency_mhz`), `reason`, `is_active`

### monitoring
- `MonitoringGroup`: `name`, `description`, `is_active`, timestamps; relations: `users (M2M)`, `locations (M2M through)`, `channels (M2M)`
- `MonitoringGroupLocation`: through table with `include_all_rooms` flag
- `Group` (legacy/simple UI group): `group_number`, `title`, `hide_charts`, `slots (JSON)`, `members (M2M WirelessUnit)`
- `Performer`: `name`, `title`, `role_description`, `photo`, `is_active`, contact info, `notes`, timestamps
- `PerformerAssignment`: `performer (FK)`, `wireless_unit (FK)`, `monitoring_group (FK)`, `priority`, `notes`, `is_active`, alert prefs, audit fields
- `Alert`: persists alert events; associated to `wireless_unit`, `user`, `performer_assignment`, type/status/message/unit snapshot (kept)
- `RealTimeConnection`: per-chassis connection status: type, status, timestamps, counters

### File/Folder Layout (authoritative)

```
models/hardware/
models/location/
models/rf/
models/monitoring/
services/
```

---

## 4) UI Strategy (HTMX, No DRF)
- Server-rendered Django templates remain primary; HTMX enhances partial updates (e.g., charger grid, assignments lists, filters).
- Replace DRF viewsets with Django views:
  - List/detail views return HTML; HTMX requests return partial fragments.
  - Minimal machine-readable JSON responses (e.g., POST actions, small polling endpoints) returned via `JsonResponse`.
- Endpoints:
  - Devices: chassis/unit lists, filtered by manufacturer/location/group.
  - Assignments: create/update/delete via HTMX forms; partials update relevant sections.
  - Alerts: acknowledge/resolve via POST; partial counters/rows update.
  - Charger dashboard: HTMX fragment for grid; size/width updates via POST JSON.
- Remove any SPA frameworks; keep to Django templates + HTMX.

---

## 5) Services Layer & Signals Strategy
- Services structure under `services/` (modules reflect domains and cross-cutting concerns):
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
- Signals:
  - Delete device-related signals; move side-effects to explicit service calls (e.g., call `DeviceService.handle_chassis_save` from model `save()` or from views/commands).
  - Delete `user_signals` (profile last_login update) and replace with middleware-based or service-invoked update during authenticated requests (e.g., lightweight `UserActivityMiddleware` that updates `UserProfile.last_login` once per session boundary).
  - Keep no signals unless a behavior is technically impossible elsewhere (none identified).

---

## 6) Legacy/Stale Component Cleanup
- Delete DRF layer:
  - Remove `micboard/viewsets.py`.
  - Remove `micboard/serializers/` (all DRF serializers).
  - Remove `micboard/permissions/permissions.py` (DRF imports).
- Remove signals modules:
  - Delete `micboard/signals/device_signals.py`.
  - Delete `micboard/signals/user_signals.py` (replace with middleware approach).
  - Minimize `micboard/signals/__init__.py` or remove if unused.
- Remove DRF from runtime:
  - Drop `djangorestframework` from dependencies and any DRF stubs or configs.
- Rename/relocate models into new domain folders; mark old modules for deletion after migration of imports.
- Prune unused optional GraphQL scaffolding (keep optional deps but do not wire until needed).

---

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
- After relocation, update imports in views/services to reference new `models/...` paths.
- Maintain app labels consistently; no migrations generated.

---

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

---

## 9) HTMX Endpoints Summary (Implementation Targets)
- `GET /` dashboard: HTML; filters via query params; HTMX fragments for device tiles.
- `GET /chargers/` dashboard: HTML; HTMX partial for grid; `POST` updates to display width (returns fragment/redirect).
- `Assignments` (`/assignments/`, CRUD): HTML forms; HTMX form submissions returning list/table fragments.
- `Alerts` (`/alerts/`, actions): list/detail HTML; POST actions acknowledge/resolve returning fragments.
- `Connection health`: small JSON endpoints in Django views (no DRF) for heartbeat/unhealthy lists, used by HTMX or lightweight polling.

This plan is authoritative for Phase 3 implementation. Do not modify this file during Phase 3.
