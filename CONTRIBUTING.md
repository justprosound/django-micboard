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

2. **Create a virtual environment with `uv`**:
   ```bash
   uv venv .venv
   source .venv/bin/activate
   ```

3. **Install development dependencies (with `uv`)**:
   ```bash
   uv pip install -e ".[dev,all]"
   ```

4. **Install pre-commit hooks** (strongly recommended):
   ```bash
   pre-commit install
   ```

### Running Tests Locally

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_conf.py -v

# Run with coverage report
pytest --cov=micboard --cov-report=html:htmlcov

# Run only unit tests (fast)
pytest -m unit

# Run integration tests (slower, includes DB)
pytest -m integration
```

Test coverage must remain **above 85%** (enforced in CI).

### Code Quality & Linting

We use `ruff` for linting, formatting, and import organization:

```bash
# Check for linting issues
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code
ruff format .

# Type checking with mypy
mypy micboard

# Security scanning with bandit
bandit -r micboard -ll
```

**Pre-commit hooks** will run automatically:

```bash
# Install hooks (one-time setup)
pre-commit install

# Run manually
pre-commit run --all-files
```

## Architecture & Code Patterns

Read [micboard/ARCHITECTURE.md](micboard/ARCHITECTURE.md) for:
- Plugin architecture for manufacturer-specific code
- Settings registry for configuration management
- Multi-tenancy patterns
- Model organization by domain

### Key Patterns to Follow

1. **Use SettingsRegistry for app configuration**, not direct `settings.get()`:
   ```python
   from micboard.conf import config

   if config.msp_enabled:
       ...
   ```

2. **Extend base classes** rather than duplicating code:
   ```python
   from micboard.services.shared.base_crud import BaseCRUDService
   class MyService(BaseCRUDService):
       ...
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

**This is a reusable app with live production users. Migrations are protected.**

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
   python manage.py makemigrations micboard
   ```
3. **Review the generated migration**:
   ```bash
   git diff micboard/migrations/
   ```
4. **Test both forward and backward** (if rolling back):
   ```bash
   python manage.py migrate
   python manage.py migrate micboard zero  # Test reverse
   python manage.py migrate  # Forward again
   ```
5. **Document decisions** in commit message
6. **Never modify existing migrations** – create a new one if needed

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
   pytest --cov=micboard --cov-fail-under=85
   pre-commit run --all-files
   mypy micboard
   bandit -r micboard -ll
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
   - [ ] Tests pass (`pytest` and `pre-commit`)
   - [ ] Documentation updated
   - [ ] Migrations reviewed (if applicable)
   - [ ] No breaking changes (or clearly documented)
   - [ ] Related issues referenced

## Multi-Tenancy Testing

If your change affects multi-tenant behavior:

```python
from django.test import TestCase
from micboard.models import Organization

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
2. Bump version (CalVer: YY.MM.DD)
3. Update `[Unreleased]` to new version with date
4. Run full test suite and linting
5. Build and publish to PyPI
6. Tag release on GitHub

## Questions?

- **Usage questions**: [GitHub Discussions](https://github.com/justprosound/django-micboard/discussions)
- **Bug reports**: [GitHub Issues](https://github.com/justprosound/django-micboard/issues)
- **Security issues**: Email security@justprosound.com (not public issues)

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0-or-later license.
