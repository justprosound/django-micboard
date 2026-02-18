# Contributing to django-micboard

Thank you for considering contributing to django-micboard! This is a community-driven open source project, and contributions from anyone are welcome.

## Code of Conduct

Be respectful and inclusive. We're all here to learn and improve the project together.

## How to Contribute

### Reporting Bugs

Open an issue on GitHub with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (Python version, Django version, OS)

### Suggesting Features

Open an issue with:
- Clear description of the feature
- Use cases and benefits
- Potential implementation approach (if you have ideas)

### Contributing Code

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** following the guidelines below
4. **Run tests**: `pytest tests/ -v`
5. **Run linters**: `ruff check . && ruff format .`
6. **Commit your changes**: Use clear, descriptive commit messages
7. **Push to your fork**: `git push origin feature/your-feature-name`
8. **Open a Pull Request**

## Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/django-micboard.git
cd django-micboard

> **LEGACY/REFERENCE ONLY: Environment setup and install instructions below use legacy `pip`/`venv`. These must NOT be used for new development/onboarding. Use `uv` only. These steps are preserved for historical reference.**

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install development dependencies
pip install -e .[dev]

# Install pre-commit hooks (optional but recommended)
pre-commit install

# Run tests
pytest tests/ -v
```

## Coding Standards

### Python Code

- **Python 3.9+** minimum
- **Type hints** for all function signatures
- **Docstrings** for all modules, classes, and public functions (Google style)
- **Keyword-only parameters** (`*`) for optional/boolean arguments
- Follow **PEP 8** (enforced by ruff)

Example:
```python
def serialize_receiver(receiver: Receiver, *, include_extra: bool = False) -> dict:
    """
    Serialize a receiver to dictionary format.

    Args:
        receiver: Receiver instance to serialize
        include_extra: Include extra metadata

    Returns:
        Dictionary with receiver data
    """
    data = {
        "id": receiver.id,
        "name": receiver.name,
    }
    if include_extra:
        data["extra"] = {}
    return data
```

### Django Code

- Use **custom model managers** for common queries
- **DRY principle**: Use shared serialization functions from `micboard/serializers.py`
- **Rate limiting**: Add `@rate_limit_view` to all public API endpoints
- **Migrations**: Add migrations as needed for model changes

### Tests

- Add tests for new functionality
- Maintain **100% test pass rate**
- Use **pytest** and **pytest-django**
- Place tests in `tests/` directory

### Documentation

- Update README.md for major changes
- Update relevant .md files in `docs/`
- Add docstrings to new code
- Use type hints for auto-generated API docs

## Pull Request Process

1. **Ensure all tests pass**: `pytest tests/ -v`
2. **Ensure linting passes**: `ruff check . && ruff format . && mypy micboard/`
3. **Update documentation** as needed
4. **Write clear PR description** explaining changes and motivation
5. **Reference related issues** if applicable

### PR Title Format

Use conventional commits format:
- `feat: Add new feature`
- `fix: Fix bug in X`
- `docs: Update documentation for Y`
- `test: Add tests for Z`
- `refactor: Refactor component A`
- `chore: Update dependencies`

## Versioning & Release Process

This project uses **Calendar Versioning** (CalVer) with format **YY.MM.DD**.

### CalVer Format

- **YY**: Two-digit year (e.g., `25` for 2025, `26` for 2026)
- **MM**: Two-digit month (e.g., `01` for January, `10` for October)
- **DD**: Two-digit day (e.g., `17` for the 17th)

**Examples:**
- `25.10.17` - Released October 17, 2025
- `26.01.22` - Released January 22, 2026

### Version Locations

The version **must be synchronized** in two locations:

1. **`micboard/__init__.py`**:
   ```python
   __version__ = "26.01.22"  # CalVer: YY.MM.DD
   ```

2. **`pyproject.toml`**:
   ```toml
   [project]
   version = "26.01.22"  # CalVer: YY.MM.DD
   ```

### Release Checklist

When preparing a release:

1. **Update Version Numbers**
   ```bash
   # Update both files with new CalVer date
   vim micboard/__init__.py
   vim pyproject.toml
   ```

2. **Update Changelog**
   ```bash
   # Add release notes to docs/changelog.md
   vim docs/changelog.md
   ```

3. **Run Full Test Suite**
   ```bash
   pytest micboard/tests/ -v
   ruff check micboard/
   mypy micboard/
   ```

4. **Commit Release**
   ```bash
   git add micboard/__init__.py pyproject.toml docs/changelog.md
   git commit -m "chore: bump version to YY.MM.DD"
   ```

5. **Create Git Tag**
   ```bash
   # Tag format: vYY.MM.DD
   git tag -a v26.01.22 -m "Release 26.01.22"
   git push origin v26.01.22
   ```

6. **Build & Publish** (Maintainers only)
   ```bash
   # Build distribution
   python -m build

   # Upload to PyPI
   twine upload dist/*
   ```

### Why CalVer?

- **Clear release dates**: Version instantly tells when code was released
- **No breaking change confusion**: No major.minor.patch ambiguity
- **Natural progression**: Always increases over time
- **Industry standard**: Used by Ubuntu, pip, setuptools, etc.

### Changelog Format

Each release entry in `docs/changelog.md` should include:

```markdown
## [26.01.22] - 2026-01-22

### Added
- New feature X for manufacturer Y
- Support for device type Z

### Changed
- Improved performance of polling service
- Updated dependency versions

### Fixed
- Bug causing devices to not appear
- WebSocket reconnection issues

### Deprecated
- Old signal-based refresh (use PollingService instead)

### Security
- Updated vulnerable dependency ABC to v2.0.0
```

## Questions?

Open an issue for discussion or questions about contributing!
