# Contributing to django-micboard

Thank you for your interest in contributing! This document provides guidelines for development, testing, and submitting contributions.

## Code of Conduct

This project adheres to the [Django Community Code of Conduct](https://www.djangoproject.com/conduct/). By participating, you're expected to uphold this code.

## Getting Started

### Development Environment Setup

> ⚠️ **MANDATORY: Use `uv` for all environment and dependency management**
>
> - You must use `uv` exclusively. `pip`, `venv`, `pipx`, and `poetry` are forbidden for all installs, environment setup, or troubleshooting in this project. If you encounter any documentation, code, or advice referencing these, IMMEDIATELY halt and update it to use `uv` instead.
> - If unsure, see AGENTS.md for policy/resilience steps and report the issue to maintainers.

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/your-username/django-micboard.git
   cd django-micboard
   ```

2. **Create the managed environment and install all supported extras**:
   ```bash
   uv sync --all-extras
   ```

3. **Install pre-commit hooks** (strongly recommended):
   ```bash
   uv run --no-sync pre-commit install
   ```

### Running Tests Locally

```bash
# Run all tests
uv run --no-sync pytest

# Run specific test file
uv run --no-sync pytest tests/test_settings_service.py -v

# Run with coverage report
just coverage

# Run only unit tests (fast)
uv run --no-sync pytest -m unit

# Run integration tests (slower, includes DB)
uv run --no-sync pytest -m integration
```

CI enforces a **95% branch-coverage** non-regression floor across every distributable Python
module. Run `just coverage` before opening a pull request.

### Model Factories

Import concrete factories from their domain modules when the model is known:

```python
from tests.factories.hardware import WirelessChassisFactory

chassis = WirelessChassisFactory(status="online")
```

Generic test helpers can resolve a factory through the live model registry:

```python
from micboard.models.hardware.wireless_unit import WirelessUnit
from tests.factories.registry import factory_for

unit = factory_for(WirelessUnit).create()
```

The catalog follows the installed application set, including optional multitenancy models, and
uses the host project's configured user model. Every new concrete project model must add a
registered factory; the factory contract test reports missing or duplicate adapters.

### Code Quality & Linting

We use `ruff` for linting, formatting, and import organization:

```bash
# Check for linting issues
uv run --no-sync ruff check .

# Auto-fix linting issues
uv run --no-sync ruff check . --fix

# Format code
uv run --no-sync ruff format .

# Type checking with mypy
uv run --no-sync python -m mypy micboard

# Security scanning with bandit
uv run --no-sync bandit -r micboard -ll
```

**Pre-commit hooks** will run automatically:

```bash
# Install hooks (one-time setup)
uv run --no-sync pre-commit install

# Run manually
uv run --no-sync pre-commit run --all-files
```

## Architecture & Code Patterns

Read [micboard/ARCHITECTURE.md](micboard/ARCHITECTURE.md) for:
- Plugin architecture for manufacturer-specific code
- Settings registry for configuration management
- Multi-tenancy patterns
- Model organization by domain

### Key Patterns to Follow

1. **Use the unified settings service**, not direct Django settings reads:
   ```python
   from micboard.services.settings.settings_service import settings as micboard_settings

   if micboard_settings.msp_enabled:
       ...
   ```

2. **Call domain services** rather than duplicating business logic in views, admin, tasks, or serializers:
   ```python
   from micboard.services.shared.base_dto import PydanticBaseDTO

   class DeviceDTO(PydanticBaseDTO):
       api_device_id: str
   ```

3. **Add type hints** to all public functions:
   ```python
   def process_devices(self, device_ids: list[int], org: Organization) -> dict[str, Any]:
       ...
   ```

4. **Document scope requirements** for multi-tenant code:
   ```python
   def get_tenant_devices(self, *, tenant: Tenant) -> QuerySet:
       """Get devices for a specific tenant.

       Args:
           tenant: Required for tenant isolation
       """
       ...
   ```

5. **Use plugin registry** for manufacturer-agnostic behavior:
   ```python
   from micboard.services.manufacturer.plugin_registry import PluginRegistry

   plugin = PluginRegistry.get_plugin('shure', manufacturer=mfg)
   devices = plugin.get_devices()
   ```

## ⚠️ CRITICAL: Database Migrations

**This is a pre-production reusable app, but migration history is protected.**

### Migration Rules

✅ **ALLOWED:**
- Creating NEW migrations for genuinely new schema changes
- Adding new fields to models (if absolutely necessary)
- Adding new indexes
- Documenting migrations with clear, descriptive messages

❌ **NEVER:**
- Manually editing existing migration files
- Deleting migration files
- Rolling back migrations carelessly
- Modifying schema without careful review

### Migration Workflow

1. **Make your model changes** in `micboard/models/`
2. **Run makemigrations** (if schema changes):
   ```bash
   uv run --no-sync python manage.py makemigrations micboard
   ```
3. **Review the generated migration**:
   ```bash
   git diff micboard/migrations/
   ```
4. **Test both forward and backward** (if rolling back):
   ```bash
   uv run --no-sync python manage.py migrate
   uv run --no-sync python manage.py migrate micboard zero  # Test reverse
   uv run --no-sync python manage.py migrate  # Forward again
   ```
5. **Document decisions** in commit message
6. **Never modify existing migrations** – create a new one if needed

Production hosts using the `standard` extra should add `django_safemigrate` to
`INSTALLED_APPS` and apply migrations through its deployment-aware command:

```bash
uv run --no-sync python manage.py safemigrate
```

The repository keeps Django-generated migrations unchanged. Do not add safety metadata by hand.

**Migration Review Checklist:**
- [ ] Migration creates/modifies what was intended
- [ ] Data loss is acceptable (confirm if needed)
- [ ] Backward compatibility (for intermediate versions)
- [ ] Performance impact considered (indexes, large data moves)
- [ ] Tested on both small and large datasets

**Release prep note:** This workflow does not edit or regenerate migrations. Any schema
changes must follow the controlled migration process above.

## Pull Request Process

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes** following code patterns above

3. **Write tests** for new functionality:
   - Add tests in `tests/`
   - Use existing test style (Django TestCase or pytest)
   - Include docstrings explaining test intent
   - Test both happy path and edge cases

4. **Run full test suite** before pushing:
   ```bash
   just coverage
   uv run --no-sync pre-commit run --all-files
   uv run --no-sync python -m mypy micboard
   uv run --no-sync bandit -r micboard -ll
   ```

5. **Update documentation**:
   - Add/update docstrings in code
   - Update CHANGELOG.md under `[Unreleased]`
   - Update README.md if user-facing
   - Add type hints throughout

6. **Commit with clear messages**:
   ```bash
   git commit -m "feat: add new manufacturer plugin support

   - Implement ManufacturerPlugin base for extensibility
   - Add plugin registry caching
   - Document plugin development guide

   Fixes #123"
   ```

   **Commit format** (Conventional Commits):
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation
   - `test:` Add/update tests
   - `refactor:` Code improvement without behavior change
   - `perf:` Performance improvement
   - `chore:` Maintenance, deps, tooling

7. **Push and open a PR**:
   ```bash
   git push origin feature/my-feature
   # Then create PR on GitHub
   ```

8. **PR checklist**:
   - [ ] Title is clear and descriptive
   - [ ] Description explains what and why
   - [ ] Tests pass (`just test` and `just pre-commit`)
   - [ ] Documentation updated
   - [ ] Migrations reviewed (if applicable)
   - [ ] No breaking changes (or clearly documented)
   - [ ] Related issues referenced

## Multi-Tenancy Testing

If your change affects multi-tenant behavior:

```python
from django.test import TestCase
from micboard.multitenancy.models import Organization

class MyMultiTenantTest(TestCase):
    def test_tenant_isolation(self):
        """Verify data isolation between tenants."""
        org1 = Organization.objects.create(name="Org 1")
        org2 = Organization.objects.create(name="Org 2")

        # Create data in org1
        device1 = Device.objects.create(org=org1, ...)

        # Verify org2 can't see it
        self.assertNotIn(device1, Device.objects.filter(org=org2))
```

## Reporting Issues

Use [GitHub Issues](https://github.com/justprosound/django-micboard/issues) to report:
- Bugs (with minimal reproduction steps)
- Feature requests (with use case description)
- Documentation improvements
- Performance concerns

Include:
- Django version
- Python version
- Steps to reproduce (for bugs)
- Expected vs actual behavior
- Error messages/logs

## Release Process

Maintainers follow this process:

1. Collect changes in `CHANGELOG.md` under `[Unreleased]`
2. Run the **Prepare Release PR** workflow from `main`; it selects the next UTC CalVer
   (`YY.MM.DD`, then `.1`, `.2`, and so on for additional same-day releases), or accepts an
   explicit backfill version
3. Let the workflow open a release pull request and dispatch CI and documentation checks
4. Let protected-branch auto-merge merge the pull request only after every required check passes
5. Let the workflow publish the exact merge commit to TestPyPI or PyPI through trusted publishing
6. Confirm that the publication workflow creates the matching GitHub release and tag

Release preparation never pushes directly to `main` and never receives an OIDC publishing token.
The separate publication workflow accepts only a commit already merged into protected `main` and
uses the appropriate protected GitHub environment for package publication.

## Questions?

- **Usage questions**: [GitHub Discussions](https://github.com/justprosound/django-micboard/discussions)
- **Bug reports**: [GitHub Issues](https://github.com/justprosound/django-micboard/issues)
- **Security issues**: Email security@justprosound.com (not public issues)

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0-or-later license.
