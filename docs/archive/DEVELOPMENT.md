# Django Micboard - Development & Release Guide

## Overview

This document provides comprehensive guidance for developing, testing, and releasing Django Micboard with a focus on code quality, test coverage (95%+ target), and CalVer versioning.

## Quick Start

> **LEGACY/REFERENCE ONLY: The setup steps below use legacy `pip` and `venv`. These are not permitted in current workflows. Use `uv` for all new environments. Legacy steps remain here for historical/archive reasons.**

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/django-micboard.git
cd django-micboard

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all extras
pip install -e ".[dev,test,docs]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests with coverage
pytest tests/ -v

# Run specific test class
pytest tests/test_models.py::TestReceiverModel -v

# Run only fast unit tests
pytest tests/ -m unit -v

# Run with coverage report
pytest --cov=micboard --cov-report=html tests/

# Generate coverage badge
coverage-badge -o docs/coverage.svg
```

### Code Quality

```bash
# Run pre-commit checks
pre-commit run --all-files

# Format code with Black
black micboard tests

# Sort imports with isort
isort micboard tests

# Type check with mypy
mypy micboard --ignore-missing-imports

# Lint with flake8
flake8 micboard tests

# Security check with Bandit
bandit -r micboard -ll
```

## Architecture & Design Patterns

### Services Layer (Preferred)

The project uses a **services layer** to handle business logic, reducing reliance on Django signals and improving testability:

```python
from micboard.services import DeviceService, SynchronizationService

# Create or update device
receiver, created = DeviceService.create_or_update_receiver(
    manufacturer=manufacturer,
    location=location,
    device_id="rx_001",
    name="Receiver 1",
    battery_level=85,
)

# Sync devices from API
stats = SynchronizationService.sync_devices(
    manufacturer_code="shure",
    location=location,
)
```

### DRY Principles

1. **Centralized Serialization**: Use functions in `micboard/serializers.py`
2. **Services for Business Logic**: Keep models thin, push logic to services
3. **Reusable Factories**: Use pytest factories from `tests/conftest.py`
4. **Common Utilities**: Extract repeated code to utilities module

### Plugin Architecture

Manufacturer implementations follow a standard plugin interface:

```python
from micboard.manufacturers import get_manufacturer_plugin

plugin = get_manufacturer_plugin("shure")
devices = plugin.get_devices()  # Returns device data
details = plugin.get_device_details("device_id")  # Device-specific info
```

## Testing Strategy

### Coverage Targets

- **Unit Tests**: 85% of code (isolated components)
- **Integration Tests**: 10% of code (plugin interactions)
- **E2E Tests**: 5% of code (full workflows)
- **Overall Target**: 95%+ code coverage

### Test Types

#### Unit Tests (Fast, Isolated)
```python
@pytest.mark.unit
class TestDeviceService:
    def test_create_receiver(self, manufacturer, location):
        receiver, created = DeviceService.create_or_update_receiver(...)
        assert created is True
```

#### Integration Tests (Plugin + Models)
```python
@pytest.mark.integration
class TestSynchronizationService:
    def test_sync_devices(self, manufacturer, mock_shure_plugin):
        stats = SynchronizationService.sync_devices(...)
        assert stats["created"] > 0
```

#### End-to-End Tests (Full Workflows)
```python
@pytest.mark.e2e
class TestPollingWorkflow:
    def test_full_polling_cycle(self, django_db_blocker):
        # Full workflow: API → Sync → Model → Signal
        pass
```

### Test Fixtures

Common fixtures from `tests/conftest.py`:

```python
# User fixtures
admin_user, staff_user, regular_user

# Model fixtures
manufacturer, location, receiver, transmitter

# Mock fixtures
mock_shure_plugin, mock_sennheiser_plugin, mock_manufacturer_registry

# Helper fixtures
assert_helpers, request_factory
```

### Writing Tests

1. **Use descriptive names**: `test_receiver_creation_sets_defaults()`
2. **Test one thing**: One assertion per test (or related assertions)
3. **Use fixtures**: Avoid setup/teardown boilerplate
4. **Mark appropriately**: `@pytest.mark.unit`, `@pytest.mark.integration`
5. **Test edge cases**: Boundary values, error conditions, validation

```python
@pytest.mark.unit
class TestReceiverValidation:
    def test_battery_level_minimum(self, receiver):
        receiver.battery_level = -1
        with pytest.raises(ValidationError):
            receiver.full_clean()

    def test_battery_level_maximum(self, receiver):
        receiver.battery_level = 101
        with pytest.raises(ValidationError):
            receiver.full_clean()

    def test_battery_level_valid_range(self, receiver):
        receiver.battery_level = 50
        receiver.full_clean()  # Should not raise
```

## Versioning & Release

### CalVer Format

Django Micboard uses Calendar Versioning (CalVer) in the format `YY.MM.DD`:

- `25.01.15` = Release on January 15, 2025
- `25.01.15.post1` = Post-release patch
- `25.01.15a1` = Pre-release (alpha)
- `25.01.15rc1` = Release candidate

### Release Process

1. **Ensure all tests pass**:
   ```bash
   pytest tests/ --cov-fail-under=85
   ```

2. **Update version** in `pyproject.toml`:
   ```toml
   [project]
   version = "25.01.15"
   ```

3. **Update CHANGELOG.md**:
   ```markdown
   ## [25.01.15] - 2025-01-15

   ### Added
   - New device synchronization service

   ### Fixed
   - Battery level validation edge case

   ### Changed
   - Refactored signal handlers to services layer
   ```

4. **Tag release**:
   ```bash
   git tag -a v25.01.15 -m "Release 25.01.15"
   git push origin v25.01.15
   ```

5. **Build and publish**:
   ```bash
   python -m build
   twine upload dist/*
   ```

Or use GitHub Actions:

```bash
# Trigger release workflow
gh workflow run release.yml -f version=25.01.15 -f prerelease=false
```

### Pre-Release Testing

For pre-releases, test with TestPyPI first:

```bash
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ django-micboard
```

## Continuous Integration

### GitHub Actions Workflows

1. **CI Pipeline** (`.github/workflows/ci.yml`):
   - Runs on every PR and push
   - Tests on Python 3.9-3.12, Django 4.2-5.0
   - Generates coverage reports
   - Runs pre-commit linting

2. **Release Pipeline** (`.github/workflows/release.yml`):
   - Manual workflow dispatch
   - Validates CalVer format
   - Runs full test suite
   - Publishes to PyPI
   - Creates GitHub release

### Local Pre-Commit

```bash
# Run all pre-commit checks
pre-commit run --all-files

# Run specific check
pre-commit run black --all-files
```

## Code Quality Targets

| Metric | Target | Current |
|--------|--------|---------|
| Code Coverage | 95% | — |
| Test Count | 150+ | — |
| Linting Errors | 0 | — |
| Type Check Passing | 95% | — |
| Security Issues | 0 | — |

## Common Tasks

### Adding a New Feature

1. Create feature branch:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Write tests first (TDD):
   ```bash
   pytest tests/test_my_feature.py -v
   ```

3. Implement feature with services:
   ```python
   # micboard/services.py
   class MyService:
       @staticmethod
       def my_operation(...):
           pass
   ```

4. Update serializers if needed:
   ```python
   # micboard/serializers.py
   def serialize_my_model(instance):
       pass
   ```

5. Run full test suite:
   ```bash
   pytest tests/ --cov=micboard
   ```

6. Commit and push:
   ```bash
   git add .
   git commit -m "feat: add my feature"
   git push origin feature/my-feature
   ```

7. Create pull request

### Adding a New Manufacturer Plugin

1. Create plugin directory:
   ```bash
   mkdir -p micboard/manufacturers/mynew_vendor
   ```

2. Implement plugin interface:
   ```python
   # micboard/manufacturers/mynew_vendor/__init__.py
   from micboard.manufacturers import ManufacturerPlugin

   class MyVendorPlugin(ManufacturerPlugin):
       code = "mynew_vendor"
       name = "My Vendor API"

       def get_devices(self):
           pass

       def get_device_details(self, device_id):
           pass
   ```

3. Register plugin:
   ```python
   # micboard/manufacturers/__init__.py
   MANUFACTURERS = {
       "mynew_vendor": MyVendorPlugin,
   }
   ```

4. Add tests:
   ```python
   # tests/test_manufacturers_mynew_vendor.py
   @pytest.mark.plugin
   class TestMyVendorPlugin:
       def test_get_devices(self):
           pass
   ```

### Debugging

```bash
# Run single test with verbose output and print statements
pytest tests/test_models.py::TestReceiverModel::test_receiver_creation -vv -s

# Run with debugger
pytest tests/test_models.py -vv -s --pdb

# Profile test performance
pytest tests/ --profile

# Generate test coverage HTML report
pytest --cov=micboard --cov-report=html
open htmlcov/index.html
```

## Database Migrations

```bash
# Create migration
python manage.py makemigrations micboard

# Apply migrations
python manage.py migrate

# Show migration SQL
python manage.py sqlmigrate micboard 0001
```

## Documentation

- **README.md**: Project overview
- **CONTRIBUTING.md**: Contribution guidelines
- **ARCHITECTURE.md**: System architecture
- **CHANGELOG.md**: Version history
- **docs/**: Extended documentation (API, plugins, etc.)

## Support & Issues

- **Bug Reports**: GitHub Issues with reproduction steps
- **Feature Requests**: GitHub Discussions or Issues
- **Pull Requests**: Welcome! Follow coding standards
- **Security**: Report to security@example.com

## Resources

- [Django Documentation](https://docs.djangoproject.com/)
- [Pytest Documentation](https://docs.pytest.org/)
- [CalVer Specification](https://calver.org/)
- [Pre-Commit Documentation](https://pre-commit.com/)
- [PyPI Packaging Guide](https://packaging.python.org/)
