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
Manufacturer APIs → ManufacturerPlugin → poll_devices → Models → WebSocket
```

- **Manufacturer APIs**: External APIs for device communication (Shure System API, etc.)
- **ManufacturerPlugin**: Plugin interface for manufacturer-specific implementations
- **poll_devices**: Management command that polls APIs, updates models, broadcasts via Channels
- **WebSocket**: Real-time updates to frontend via Django Channels

### Package Structure
```
micboard/
├── manufacturers/          # Plugin architecture for multi-manufacturer support
│   ├── __init__.py         # Plugin registration and discovery
│   ├── shure/              # Shure-specific implementation
│   └── sennheiser/         # Sennheiser-specific implementation
├── admin/                  # Django admin interfaces
├── models/                 # Django models (manufacturers, devices, assignments, locations)
├── views/                  # REST API and dashboard views
├── serializers.py          # Centralized serialization
└── decorators.py           # Rate limiting decorators
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


Do not include or update tests in this phase.
Do not maintain backward compatibility.

### Phase 2: Core Feature Implementation
Implement core features for django-micboard:
# Django Micboard — AI agent instructions (concise)

This file gives actionable, repo-specific guidance for automated coding agents working on django-micboard. Keep instructions short and strictly tied to discoverable project patterns.

1. Big picture
    - Micboard is a Django app for real-time, multi-vendor wireless microphone monitoring. Data flows: vendor API clients -> manufacturer plugins (micboard/manufacturers) -> polling command (`micboard/management/commands/poll_devices.py`) -> models (`micboard/models/*`) -> WebSocket broadcasts (Django Channels in `micboard/websockets/`).

2. Key directories & files to consult (fast)
    - `micboard/manufacturers/` — plugin registration and per-vendor implementations (see `shure/`, `sennheiser/`).
    - `micboard/management/commands/poll_devices.py` — polling orchestration; updating models and broadcasting.
    - `micboard/serializers.py` — central serializers; prefer these for API and WS payloads.
    - `micboard/decorators.py` — rate-limiting utilities used by API views.
    - `micboard/models/` — domain models and custom managers (e.g., active/online helpers).
    - `micboard/websockets/` and `micboard/signals/` — real-time update handlers.

3. Project-specific conventions (do not invent alternatives)
    - Use manufacturer plugins via the registered factory (`micboard.manufacturers.get_manufacturer_plugin`). Example: plugin.get_devices()
    - Serialization is centralized. Always call functions in `micboard/serializers.py` instead of ad-hoc dicts.
    - Optional/boolean args use keyword-only params (use `*` in signatures).
    - API views must use rate limiting decorators from `micboard.decorators`.
    - Long-running tasks and polling are expected to run via management commands or Django-Q tasks; avoid synchronous blocking in views.

4. Developer workflows and commands (verified from repo)
    - Run tests: `pytest tests/ -v` (many tests depend on settings in `tests/settings.py`).
    - Start polling locally (for integration behavior): `python manage.py poll_devices`.
    - Docker demo available in `demo/docker/` (use that to reproduce environment).

5. Integration points & external dependencies
    - Vendor APIs: shure and sennheiser integrations under `micboard/integrations` and `micboard/manufacturers`.
    - Django Channels used for WS broadcasts; inspect `micboard/websockets` and ASGI config under `demo/asgi.py`.
    - Optional task queue: project expects Django-Q patterns in `micboard/tasks` (search for `django_q` usage).

6. Concrete examples to copy when coding
    - Fetch plugin devices: `from micboard.manufacturers import get_manufacturer_plugin; plugin = get_manufacturer_plugin(code); devices = plugin.get_devices()`
    - Use serializer helper: `from micboard.serializers import serialize_receivers; payload = serialize_receivers(receivers, include_extra=True)`
    - Decorate views: `@rate_limit_view(max_requests=120, window_seconds=60)` (see `micboard/decorators.py`).

7. What to avoid / common pitfalls (observed in tests/docs)
    - Don't bypass `serializers.py`.
    - Don't call device hardware directly — always go through the manufacturer plugin.
    - Missing docstrings and typing may fail CI/tests; follow existing style (`from __future__ import annotations`).

8. When to run tests / linting
    - After any behavioral change run `pytest tests/ -q` and fix failing tests. Tests are authoritative.

9. If uncertain
    - Prefer small, localized changes and add or update tests under `tests/` that demonstrate intended behavior.
    - If a plugin/market-specific behavior is unclear, open a short PR or issue referencing `micboard/manufacturers/*` and `micboard/management/commands/poll_devices.py`.

Please review — if anything is unclear or you want a stricter style (e.g., stricter typing, test templates, or more examples), tell me which sections to expand.
Do not include or update tests in this phase.
