# Django Micboard - AI Agent Instructions

## Project Overview
Open source Django app for real-time multi-manufacturer wireless microphone monitoring. Integrates with manufacturer APIs (Shure, Sennheiser, etc.) for device communication.

**Status:** Active development, not production-ready
**Target:** Django 4.2+/5.0+, Python 3.9+
**Version:** CalVer (YY.MM.DD) - Current: 25.10.17
**License:** AGPL-3.0-or-later

## Architecture

### Data Flow
```
Manufacturer APIs → ManufacturerPlugin → Services → Models → Signals → WebSocket
                                           ↓
                                    Business Logic
```

- **Manufacturer APIs**: External APIs for device communication (Shure System API, etc.)
- **ManufacturerPlugin**: Plugin interface for manufacturer-specific implementations
- **Services**: Business logic layer (Phase 1: COMPLETE - 69 methods)
- **Models**: Django models (domain objects)
- **Signals**: Audit logging and cross-app notifications (minimal)
- **WebSocket**: Real-time updates to frontend via Django Channels

### Package Structure
```
micboard/
├── services/               # ✅ Business logic layer (Phase 1: COMPLETE)
│   ├── __init__.py         # Service exports and documentation
│   ├── device.py           # DeviceService (11 methods)
│   ├── assignment.py       # AssignmentService (8 methods)
│   ├── manufacturer.py     # ManufacturerService (7 methods)
│   ├── connection.py       # ConnectionHealthService (11 methods)
│   ├── location.py         # LocationService (9 methods)
│   ├── discovery.py        # DiscoveryService (9 methods)
│   ├── exceptions.py       # 8 domain-specific exceptions
│   └── utils.py            # Pagination, filtering, data classes
├── manufacturers/          # Plugin architecture for multi-manufacturer support
│   ├── __init__.py         # Plugin registration and discovery
│   ├── shure/              # Shure-specific implementation
│   └── sennheiser/         # Sennheiser-specific implementation
├── models/                 # Django models (manufacturers, devices, assignments, locations)
├── signals.py              # ✅ Signal handlers (audit logging only)
├── apps.py                 # ✅ App configuration (signal registration)
├── views/                  # REST API and dashboard views
├── serializers.py          # Centralized serialization
├── decorators.py           # Rate limiting decorators
├── test_utils.py           # ✅ Testing utilities (Phase 2 support)
├── management_command_template.py  # ✅ Reference implementation
└── views_template.py       # ✅ Reference implementation
```

Always use context7 when I need code generation, setup or configuration steps, or
library/API documentation. This means you should automatically use the Context7 MCP
tools to resolve library id and get library docs without me having to explicitly ask.

## Refactor Roadmap

### Phase 1: Codebase Audit & Modularization
Refactor the current django-micboard codebase to improve modularity and maintainability.

Audit for large, monolithic files and repeated logic.
Apply DRY principles.
Split logic into folders:

integrations/{manufacturer} – vendor API connectivity (e.g., Shure, Sennheiser)
discovery/ – CIDR, FQDN, IP logic
signals/ – Django signal handlers
websockets/ – Django Channels consumers
permissions/ – user group access logic
views/ – general Django views
chargers/ – charger-specific views, models, templates
tasks/ – Django-Q background jobs
api/ – DRF views, routers, permissions
serializers/ – DRF serializers
**services/ – business logic layer (see below)**

**Phase 1 Service Layer Guidelines:**
- Create `micboard/services/` for business logic extraction.
- Each service should be a plain Python class with explicit methods and type hints.
- Services operate on validated domain models; avoid tight coupling to views/serializers.
- Manufacturer operations: `ManufacturerService.sync_devices()`, `ManufacturerService.get_device_status()`
- Assignment operations: `AssignmentService.create_assignment()`, `AssignmentService.update_assignment()`
- Location/discovery operations: `DiscoveryService.discover_devices_by_cidr()`
- Connection/health monitoring: `ConnectionHealthService.check_connection_status()`
- Keep signal handlers minimal; move core logic into services first, then trigger signals if cross-app events are needed.

Do not include or update tests in this phase.
Do not maintain backward compatibility.

### Phase 2: Core Feature Implementation
Implement core features for django-micboard:
# Django Micboard — AI agent instructions (concise)

This file gives actionable, repo-specific guidance for automated coding agents working on django-micboard. Keep instructions short and strictly tied to discoverable project patterns.

1. Big picture
    - Micboard is a Django app for real-time, multi-vendor wireless microphone monitoring. Data flows: vendor API clients -> manufacturer plugins (micboard/manufacturers) -> polling command (`micboard/management/commands/poll_devices.py`) -> models (`micboard/models/*`) -> WebSocket broadcasts (Django Channels in `micboard/websockets/`).

2. Key directories & files to consult (fast)
    - `micboard/services/` — ✅ business logic layer (Phase 1: COMPLETE - 69 methods). **All operations go through services.**
    - `micboard/signals.py` — ✅ signal handlers (audit logging only, core logic in services).
    - `micboard/test_utils.py` — ✅ testing utilities (base classes, fixtures, helpers).
    - `micboard/management_command_template.py` — ✅ reference for refactoring commands.
    - `micboard/views_template.py` — ✅ reference for refactoring views.
    - `micboard/manufacturers/` — plugin registration and per-vendor implementations (see `shure/`, `sennheiser/`).
    - `micboard/management/commands/poll_devices.py` — polling orchestration; should use `ManufacturerService` and `DeviceService`.
    - `micboard/serializers.py` — central serializers; prefer these for API and WS payloads.
    - `micboard/decorators.py` — rate-limiting utilities used by API views.
    - `micboard/models/` — domain models and custom managers (e.g., active/online helpers).
    - `docs/00_START_HERE.md` — ✅ master guide for service layer.
    - `docs/services-quick-reference.md` — ✅ quick method lookup.

3. Project-specific conventions (do not invent alternatives)
    - **Use service layer for business logic**: All operations should go through `micboard.services.*` classes.
      Example: `DeviceService.sync_device_status(device_obj=receiver, online=True)`
    - Use manufacturer plugins via the registered factory (`micboard.manufacturers.get_manufacturer_plugin`). Example: plugin.get_devices()
    - Serialization is centralized. Always call functions in `micboard/serializers.py` instead of ad-hoc dicts.
    - Optional/boolean args use keyword-only params (use `*` in signatures).
    - API views must use rate limiting decorators from `micboard.decorators`.
    - Long-running tasks and polling are expected to run via management commands or Django-Q tasks; avoid synchronous blocking in views.
    - **Exception handling**: Catch service exceptions explicitly (e.g., `AssignmentAlreadyExistsError`), not generic `Exception`.

4. Developer workflows and commands (verified from repo)
    - Run tests: `pytest tests/ -v` (many tests depend on settings in `tests/settings.py`).
    - Start polling locally (for integration behavior): `python manage.py poll_devices`.
    - Docker demo available in `demo/docker/` (use that to reproduce environment).

5. Integration points & external dependencies
    - Vendor APIs: shure and sennheiser integrations under `micboard/integrations` and `micboard/manufacturers`.
    - Django Channels used for WS broadcasts; inspect `micboard/websockets` and ASGI config under `demo/asgi.py`.
    - Optional task queue: project expects Django-Q patterns in `micboard/tasks` (search for `django_q` usage).

6. Concrete examples to copy when coding (✅ Phase 1 Complete)
    - **Device operations**: `from micboard.services import DeviceService; receivers = DeviceService.get_active_receivers()`
    - **Sync device status**: `DeviceService.sync_device_status(device_obj=receiver, online=True)`
    - **Create assignment**: `from micboard.services import AssignmentService; assignment = AssignmentService.create_assignment(user=user, device=device, alert_enabled=True)`
    - **Handle exceptions**: `from micboard.services import AssignmentAlreadyExistsError; try: ... except AssignmentAlreadyExistsError as e: ...`
    - **Sync manufacturer**: `from micboard.services import ManufacturerService; result = ManufacturerService.sync_devices_for_manufacturer(manufacturer_code='shure')`
    - **Health monitoring**: `from micboard.services import ConnectionHealthService; unhealthy = ConnectionHealthService.get_unhealthy_connections(heartbeat_timeout_seconds=60)`
    - **Location ops**: `from micboard.services import LocationService; location = LocationService.create_location(name='Main Stage', description='...')`
    - **Testing**: `from micboard.test_utils import ServiceTestCase, create_test_receiver; class TestMyService(ServiceTestCase): ...`
    - **Fetch plugin devices**: `from micboard.manufacturers import get_manufacturer_plugin; plugin = get_manufacturer_plugin(code); devices = plugin.get_devices()`
    - **Serialization**: `from micboard.serializers import serialize_receivers; payload = serialize_receivers(receivers, include_extra=True)`
    - **Rate limiting**: `@rate_limit_view(max_requests=120, window_seconds=60)` (see `micboard/decorators.py`)

7. What to avoid / common pitfalls (observed in tests/docs)
    - ❌ **Don't bypass the service layer** — all business logic goes through `micboard/services/`.
    - ❌ **Don't put business logic in signals** — signals are only for audit logging/notifications.
    - ❌ **Don't use generic Exception** — catch specific exceptions from `micboard.services.exceptions`.
    - ❌ **Don't bypass `serializers.py`** — always use centralized serialization.
    - ❌ **Don't call device hardware directly** — always go through manufacturer plugins.
    - ❌ **Don't use positional args for optional params** — use keyword-only parameters (after `*`).
    - ❌ **Missing docstrings and typing may fail CI/tests** — follow existing style (`from __future__ import annotations`).

8. When to run tests / linting
    - After any behavioral change run `pytest tests/ -q` and fix failing tests. Tests are authoritative.

9. If uncertain
    - **Check docs first**: `docs/00_START_HERE.md` → `docs/services-quick-reference.md` → `docs/PHASE2_INTEGRATION_GUIDE.md`
    - **Review templates**: `micboard/management_command_template.py` or `micboard/views_template.py`
    - **Use test utilities**: `from micboard.test_utils import ServiceTestCase, create_test_receiver`
    - Prefer small, localized changes and add or update tests under `tests/` that demonstrate intended behavior.
    - If a plugin/market-specific behavior is unclear, open a short PR or issue referencing `micboard/manufacturers/*` and `micboard/management/commands/poll_devices.py`.

## ✅ Phase 1 Complete - Service Layer Ready

**69 production-ready methods** across 6 services:
- `DeviceService` (11 methods) - Device management & sync
- `AssignmentService` (8 methods) - User-device assignments
- `ManufacturerService` (7 methods) - API orchestration
- `ConnectionHealthService` (11 methods) - Connection monitoring
- `LocationService` (9 methods) - Location management
- `DiscoveryService` (9 methods) - Device discovery

**Documentation**: 14 comprehensive guides in `docs/`
**Quality**: 100% type hints, 100% docstrings, 100% keyword-only params

**Start here**: `docs/00_START_HERE.md`

Do not include or update tests in this phase.
