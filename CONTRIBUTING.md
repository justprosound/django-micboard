# Contributing to django-micboard

Thank you for your interest in contributing!

## Development Environment Setup

1. Install the package with development dependencies:
   ```bash
   pip install -e ".[dev,all]"
   ```
2. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Coding Standards

- **Linting**: We use `ruff`. Run `ruff check .` before submitting.
- **Formatting**: We use `ruff format .`.
- **Type Hints**: All new code should include PEP 484 type hints.
- **Migrations**: **CRITICAL**: Do not manually edit files in `migrations/` directories. New migrations must be generated only when schema changes are approved.

## Testing

Run the full test suite before submitting a Pull Request:
```bash
pytest
```

## Pull Request Guidelines

1. Create a feature branch from `develop`.
2. Ensure all tests pass.
3. Update documentation if you add new features.
4. Provide a clear summary of changes in your PR description.
