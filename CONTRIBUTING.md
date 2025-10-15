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

## Versioning

This project uses **Calendar Versioning** (CalVer: YY.MM.DD).

- Version is defined in `micboard/__init__.py`
- Update `docs/changelog.md` for notable changes
- Maintainers handle version bumps for releases

## Questions?

Open an issue for discussion or questions about contributing!
