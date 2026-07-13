# django-micboard

**Real-time multi-manufacturer wireless microphone monitoring for Django.**

django-micboard is a community-driven, pre-production Django reusable app for monitoring wireless audio systems (Shure, Sennheiser, etc.) in real-time. It provides device discovery, telemetry, alerting, performer assignment, and multi-tenant/multi-location support with a manufacturer-agnostic plugin architecture.

- **License**: AGPL-3.0-or-later
- **Status**: Beta (pre-production)
- **Python**: 3.13+
- **Django**: 5.1 through 6.0

## Features

- **Multi-Manufacturer Support**: Plugin architecture for Shure System API, Sennheiser SSCv2, and more
- **Real-Time Updates**: Live device telemetry via WebSockets (Channels) or SSE polls
- **Device Lifecycle**: Automated discovery, registration, tracking, and movement auditing
- **Wireless Monitoring**: Battery levels, RF signal strength, audio levels, charging status
- **Location Management**: Buildings, rooms, zones with multi-site/multi-location support
- **Performer Assignment**: Map performers to devices with activity history
- **Alert System**: User-specific notification rules for battery, signal, offline events
- **Regulatory Compliance**: Frequency band coordination and domain auditing
- **Multi-Tenant Safe**: Optional MSP (Managed Service Provider) mode with organization isolation
- **Settings Registry**: Scope-aware configuration (global → site → organization → manufacturer)
- **Admin Interface**: Beautiful Unfold admin theme with advanced filtering and history tracking

## Installation

### For End Users (Using the App)

Add to your Django project:

```bash
uv add "django-micboard[standard]"
```

Use `uv add django-micboard` instead when only the core reusable app is needed.

In `settings.py`:

```python
INSTALLED_APPS = [
    # ... Django core apps ...
    "micboard",
]

# Optionally, add these for enhanced features
INSTALLED_APPS += [
    "django.contrib.sites",  # For multi-site support
    "unfold",  # Modern admin theme
    "simple_history",  # Model change tracking
    "huey.contrib.djhuey",  # Native Huey Django integration
]

HUEY = {
    "huey_class": "huey.RedisHuey",
    "name": "micboard",
    "connection": {
        "url": os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
    },
    "immediate": DEBUG,
}

# Configure Micboard
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": os.environ.get("SHURE_API_BASE_URL", "https://localhost:10000"),
    "SHURE_API_SHARED_KEY": os.environ.get("SHURE_API_SHARED_KEY"),
    "SHURE_API_VERIFY_SSL": False,
    "POLL_INTERVAL": 5,  # seconds
}

# Optional: Enable multi-tenancy
MICBOARD_MULTI_SITE_MODE = True
MICBOARD_MSP_ENABLED = False  # or True for full MSP mode
MICBOARD_SITE_ISOLATION = "site"  # or "organization", "campus"
```

Add to your `urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    path("micboard/", include("micboard.urls", namespace="micboard")),
    # ... other patterns ...
]
```

Run migrations:

```bash
uv run --no-sync python manage.py migrate
```

Note: This release prep does not modify or generate migrations. Existing migrations remain
unchanged; host projects continue to manage database schema changes as usual.

Run the native Huey consumer with:

```bash
uv run --no-sync python manage.py run_huey
```

### For Development

> **CRITICAL: Environment & Dependency Management Policy**
>
> This project **strictly forbids** the use of `pip`, `pipx`, `poetry`, or Python's built-in `venv` for all environment and package management. **ALL** environments and dependencies must be set up and managed using [`uv`](https://github.com/astral-sh/uv) exclusively. Any documentation, code, or CI which references or suggests non-`uv` patterns must be updated or escalated to project maintainers for correction. See [CONTRIBUTING.md](CONTRIBUTING.md) for full enforcement and escalation procedure.
>
> Agents and automation are expected to enforce this pattern in all workflows.

1. **Clone the repository**:
   ```bash
   git clone https://github.com/justprosound/django-micboard.git
   cd django-micboard
   ```

2. **Create the uv-managed environment and install every supported extra**:
   ```bash
   uv sync --all-extras
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Run the example project**:
   ```bash
   cd example_project
   uv run --no-sync python manage.py migrate
   uv run --no-sync python manage.py createsuperuser
   uv run --no-sync python manage.py runserver
   ```

5. **Access the admin**:
   - http://localhost:8000/admin
   - Login with your superuser credentials

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for complete list):

```bash
# Shure API
MICBOARD_SHURE_API_BASE_URL=https://shure-api.example.com:10000
MICBOARD_SHURE_API_SHARED_KEY=your-secret-key
MICBOARD_SHURE_API_VERIFY_SSL=False
MICBOARD_SHURE_API_TIMEOUT=10

# Multi-tenancy
MICBOARD_MULTI_SITE_MODE=False
MICBOARD_MSP_ENABLED=False

# Audit & retention
MICBOARD_ACTIVITY_LOG_RETENTION_DAYS=90
```

### Using the Configuration API

```python
from micboard.services.settings import settings as micboard_settings

# Feature flags
if micboard_settings.msp_enabled:
    ...

# Get custom settings
timeout = micboard_settings.get("SHURE_API_TIMEOUT", default=10)

# Scoped settings use the same service
value = micboard_settings.get(
    "CUSTOM_KEY",
    organization=org,
    site=site,
    default="fallback",
)
```

See [micboard/ARCHITECTURE.md](micboard/ARCHITECTURE.md) for detailed architecture documentation.

## Plugin Architecture

Extend Micboard with manufacturer-specific plugins. Put each plugin in
`micboard/integrations/<code>/plugin.py`; `PluginRegistry` discovers it by module and class name.
For example, `micboard/integrations/acme/plugin.py` can contain:

```python
from typing import Any

from micboard.services.common.base.plugin import ManufacturerPlugin


class AcmePlugin(ManufacturerPlugin):
    @property
    def name(self) -> str:
        return "Acme"

    @property
    def code(self) -> str:
        return "acme"

    def get_client(self) -> object:
        return object()

    def get_devices(self) -> list[dict[str, Any]]:
        return []

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        return None

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        return []

    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        return dict(api_data)

    def is_healthy(self) -> bool:
        return True

    def check_health(self) -> dict[str, Any]:
        return {"status": "healthy"}
```

Load the class or an instance through the registry; no central registration file is required:

```python
from micboard.services.manufacturer.plugin_registry import PluginRegistry

plugin_class = PluginRegistry.get_plugin_class("acme")
plugin = PluginRegistry.get_plugin("acme", manufacturer=manufacturer)
```

## Testing

Run the test suite:

```bash
# All tests
uv run --no-sync pytest

# Specific test file
uv run --no-sync pytest tests/test_settings_diff_admin.py -v

# With coverage
just coverage

# Specific markers
uv run --no-sync pytest -m unit
uv run --no-sync pytest -m integration
uv run --no-sync pytest -m django_db
```

## Linting & Pre-commit

Use ruff and pre-commit to keep code quality consistent:

```bash
uv run --no-sync ruff check .
uv run --no-sync ruff format .
uv run --no-sync pre-commit run --all-files
```

## Release Notes

- Update CHANGELOG.md under [Unreleased] with notable changes.
- Build the package and publish to PyPI or your internal index.
- Tag releases with a calendar version (e.g., v26.01.29).

## Development Workflow

> **Agent & Research Workflow Policy**
>
> - When you need to search programming documentation, always use the `context7` tools (see AGENTS.md Quick Reference).
> - If you are unsure how to implement or use a library, use `gh_grep` to search for up-to-date code examples from GitHub.

1. **Install pre-commit hooks**:
   ```bash
   uv run --no-sync pre-commit install
   ```

2. **Run linting/formatting**:
   ```bash
   uv run --no-sync ruff check . --fix
   uv run --no-sync ruff format .
   ```

3. **Type checking**:
   ```bash
   uv run --no-sync python -m mypy micboard
   ```

4. **Run tests before committing**:
   ```bash
   uv run --no-sync pytest
   uv run --no-sync pre-commit run --all-files
   ```

5. **Security checks**:
   ```bash
   uv run --no-sync bandit -r micboard -ll
   ```

## Important Notes on Migrations

⚠️ **CRITICAL**: This is a pre-production reusable app, but migration history is protected:

- **DO NOT** manually edit files in `micboard/migrations/`
- **DO NOT** run `makemigrations` carelessly
- **ONLY** create new migrations when schema changes are approved
- **NEVER** delete or modify existing migrations
- **ALWAYS** test migrations thoroughly before production deployment
- **USE** `uv run --no-sync python manage.py safemigrate` in production hosts configured with
  `django_safemigrate`

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Documentation

- [Architecture Guide](micboard/ARCHITECTURE.md) - System design and patterns
- [Contributing Guide](CONTRIBUTING.md) - Development process
- [Changelog](CHANGELOG.md) - Release notes
- [API Documentation](docs/) - Full reference

## Support & Contributing

- **Issues**: [GitHub Issues](https://github.com/justprosound/django-micboard/issues)
- **Discussions**: [GitHub Discussions](https://github.com/justprosound/django-micboard/discussions)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

AGPL-3.0-or-later – This program is free software. See [LICENSE](LICENSE) for details.

**Note**: If you use this software in production, you may need to comply with AGPL licensing requirements, including making source code available to users.
