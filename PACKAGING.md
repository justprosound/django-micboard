# Packaging django-micboard

## Overview

This guide explains how to package and distribute django-micboard as a Python module via PyPI or GitHub.

# Packaging django-micboard

## Overview

This guide explains how to package and distribute django-micboard as a Python module via PyPI or GitHub.

## Recommended Directory Structure

For a distributable Django app, follow this standard structure:

```
django-micboard/                    # Repository root (this is where setup.py lives)
├── micboard/                       # Python package (the Django app)
│   ├── __init__.py                # Package metadata
│   ├── models.py
│   ├── views.py
│   ├── admin.py
│   ├── urls.py
│   ├── apps.py
│   ├── consumers.py
│   ├── decorators.py
│   ├── routing.py
│   ├── shure_api_client.py
│   ├── tests.py
│   ├── settings_template.py       # Reference only
│   ├── static/                    # Static assets
│   │   └── micboard/
│   ├── templates/                 # Django templates
│   │   └── micboard/
│   ├── management/                # Management commands
│   │   └── commands/
│   └── migrations/                # Database migrations
│       └── __init__.py
├── tests/                         # Optional: Tests outside package
│   ├── __init__.py
│   └── test_*.py
├── docs/                          # Optional: Sphinx documentation
│   ├── conf.py
│   └── index.rst
├── examples/                      # Optional: Example projects
│   └── basic_setup/
├── setup.py                       # Package metadata (root level)
├── pyproject.toml                # Build configuration (root level)
├── MANIFEST.in                   # File inclusion rules
├── LICENSE                       # MIT License
├── README.md                     # Main documentation
├── CHANGELOG.md                  # Version history
├── QUICKSTART.md                 # Installation guide
├── ARCHITECTURE.md               # Architecture docs
├── USER_ASSIGNMENT.md            # Feature documentation
├── RATE_LIMITING.md              # Rate limiting guide
├── PACKAGING.md                  # This file
├── requirements.txt              # For reference
├── .gitignore                    # Git ignore rules
├── .copilot-instructions.md      # Copilot guidelines
└── .github/
    └── workflows/
        └── publish.yml           # CI/CD for publishing
```

**Key points:**
- 📦 **Root level**: Packaging files, documentation, CI/CD
- 📁 **micboard/**: The actual Django app that gets installed
- 🧪 **tests/**: Optional external tests (not installed)
- 📚 **docs/**: Optional Sphinx documentation (not installed)

This structure matches popular Django packages like `django-debug-toolbar`, `django-allauth`, `django-rest-framework`.

## Restructuring Existing Installation

If your current structure has all files at the same level (app files mixed with packaging files), use the provided restructuring script:

```bash
# From the current micboard directory
bash /home/skuonen/micboard_restructure.sh
```

This will:
1. Create backup of current structure
2. Create new `django-micboard/` parent directory
3. Move app files into `micboard/` subdirectory
4. Keep packaging files at root level
5. Preserve all files and structure

## Package Structure

```
django-micboard/
├── micboard/                 # Main package directory
│   ├── __init__.py          # Package metadata (__version__, etc.)
│   ├── models.py
│   ├── views.py
│   ├── ...                  # Other app files
│   ├── static/              # Static files (included)
│   ├── templates/           # Templates (included)
│   └── management/          # Management commands (included)
├── setup.py                 # Legacy setup (backwards compatibility)
├── pyproject.toml          # Modern Python packaging
├── MANIFEST.in             # Include/exclude files
├── LICENSE                 # MIT License
├── README.md               # Package documentation
├── CHANGELOG.md            # Version history
└── requirements.txt        # Dependencies (for reference)
```

## Prerequisites

Install packaging tools:
```bash
pip install build twine
```

## Building the Package

### 1. Update Version Number

Edit `micboard/__init__.py`:
```python
__version__ = '2.2.0'  # Update this
```

Also update in `pyproject.toml` and `setup.py` if using legacy setup.

### 2. Build Distribution Files

```bash
# Clean previous builds
rm -rf build/ dist/ *.egg-info

# Build wheel and source distribution
python -m build
```

This creates:
- `dist/django-micboard-2.2.0.tar.gz` (source distribution)
- `dist/django_micboard-2.2.0-py3-none-any.whl` (wheel)

### 3. Verify Package Contents

```bash
# List contents of wheel
unzip -l dist/django_micboard-2.2.0-py3-none-any.whl

# List contents of source distribution
tar -tzf dist/django-micboard-2.2.0.tar.gz
```

Verify that static files, templates, and documentation are included.

## Publishing to PyPI

### 1. Create PyPI Account

- Register at https://pypi.org/account/register/
- Generate API token at https://pypi.org/manage/account/token/

### 2. Configure Credentials

Create `~/.pypirc`:
```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...  # Your API token
```

Or use environment variable:
```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-AgEIcHlwaS5vcmc...
```

### 3. Upload to Test PyPI (Recommended First)

```bash
# Upload to test.pypi.org
twine upload --repository testpypi dist/*

# Test installation
pip install --index-url https://test.pypi.org/simple/ django-micboard
```

### 4. Upload to Production PyPI

```bash
# Upload to pypi.org
twine upload dist/*
```

### 5. Verify Publication

```bash
# Install from PyPI
pip install django-micboard

# Or with Redis support
pip install django-micboard[redis]

# Or with dev tools
pip install django-micboard[dev]
```

## Publishing to GitHub

### 1. Create GitHub Repository

```bash
git init
git add .
git commit -m "Initial commit: django-micboard v2.2.0"
git remote add origin https://github.com/yourusername/django-micboard.git
git push -u origin main
```

### 2. Create GitHub Release

1. Go to your repository on GitHub
2. Click "Releases" → "Create a new release"
3. Tag version: `v2.2.0`
4. Release title: `django-micboard v2.2.0`
5. Description: Copy from CHANGELOG.md
6. Attach built files (optional):
   - `django-micboard-2.2.0.tar.gz`
   - `django_micboard-2.2.0-py3-none-any.whl`
7. Click "Publish release"

### 3. Install from GitHub

Users can install directly from GitHub:

```bash
# From main branch
pip install git+https://github.com/yourusername/django-micboard.git

# From specific tag
pip install git+https://github.com/yourusername/django-micboard.git@v2.2.0

# From specific branch
pip install git+https://github.com/yourusername/django-micboard.git@develop
```

## GitHub Actions for Automated Publishing

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    
    - name: Build package
      run: python -m build
    
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Add `PYPI_API_TOKEN` to GitHub Secrets:
1. Repository Settings → Secrets → Actions
2. Add new secret: `PYPI_API_TOKEN`
3. Value: Your PyPI API token

## Version Management

### Semantic Versioning

Follow semver (MAJOR.MINOR.PATCH):
- **MAJOR**: Breaking changes (e.g., 3.0.0)
- **MINOR**: New features, backwards compatible (e.g., 2.3.0)
- **PATCH**: Bug fixes, backwards compatible (e.g., 2.2.1)

### Update Checklist

Before releasing a new version:

1. ✅ Update `__version__` in `micboard/__init__.py`
2. ✅ Update version in `pyproject.toml`
3. ✅ Update version in `setup.py`
4. ✅ Update `CHANGELOG.md` with changes
5. ✅ Run tests (if available)
6. ✅ Build package: `python -m build`
7. ✅ Test locally: `pip install dist/django_micboard-*.whl`
8. ✅ Create git tag: `git tag v2.2.0`
9. ✅ Push tag: `git push origin v2.2.0`
10. ✅ Upload to PyPI: `twine upload dist/*`
11. ✅ Create GitHub release

## Private Package Distribution

### GitHub Packages (GitHub Container Registry)

1. Generate Personal Access Token with `write:packages` scope
2. Configure authentication:
   ```bash
   export GITHUB_TOKEN=ghp_...
   ```

3. Upload to GitHub Packages:
   ```bash
   twine upload --repository-url https://upload.pypi.org/legacy/ \
     --username __token__ \
     --password $GITHUB_TOKEN \
     dist/*
   ```

### Private PyPI Server

Use `devpi`, `pypiserver`, or artifact repositories (Artifactory, Nexus):

```bash
# Upload to private server
twine upload --repository-url https://pypi.yourcompany.com/simple/ dist/*

# Install from private server
pip install --index-url https://pypi.yourcompany.com/simple/ django-micboard
```

## Installation Methods

Users can install django-micboard in several ways:

### From PyPI (Recommended)
```bash
pip install django-micboard
```

### With optional dependencies
```bash
pip install django-micboard[redis]  # With Redis support
pip install django-micboard[dev]    # With development tools
```

### From GitHub
```bash
pip install git+https://github.com/yourusername/django-micboard.git
```

### From local source
```bash
cd django-micboard
pip install -e .  # Editable install for development
```

### Using requirements.txt
```txt
# requirements.txt
django-micboard==2.2.0

# Or from GitHub
git+https://github.com/yourusername/django-micboard.git@v2.2.0
```

### Using Poetry
```bash
poetry add django-micboard
```

### Using Pipenv
```bash
pipenv install django-micboard
```

## Testing the Package

Before publishing, test the package thoroughly:

```bash
# Create clean virtual environment
python -m venv test_env
source test_env/bin/activate  # or `test_env\Scripts\activate` on Windows

# Install from local wheel
pip install dist/django_micboard-2.2.0-py3-none-any.whl

# Test import
python -c "import micboard; print(micboard.__version__)"

# Create test Django project
django-admin startproject testproject
cd testproject

# Add to INSTALLED_APPS and test
python manage.py check micboard
```

## Troubleshooting

### Missing static files
- Check `MANIFEST.in` includes `recursive-include micboard/static *`
- Verify `include_package_data=True` in `setup.py`
- Check `[tool.setuptools.package-data]` in `pyproject.toml`

### Version conflicts
- Ensure version is consistent across `__init__.py`, `pyproject.toml`, and `setup.py`
- Use single source of truth: read version from `__init__.py` in `setup.py`

### Upload failures
- Verify PyPI credentials
- Check package name isn't already taken
- Ensure version number is incremented (can't reuse versions)

### Import errors after installation
- Check package name in `INSTALLED_APPS` is correct: `'micboard'`
- Verify `__init__.py` exists in package directory
- Check `default_app_config` if using Django < 3.2

## Best Practices

1. **Always test on TestPyPI first** before publishing to production
2. **Use semantic versioning** for clear version communication
3. **Document changes** in CHANGELOG.md for every release
4. **Tag releases** in git for easy rollback
5. **Sign releases** with GPG for security (optional but recommended)
6. **Automate with CI/CD** to reduce manual errors
7. **Include comprehensive documentation** in README.md
8. **Add badges** to README for build status, coverage, PyPI version, etc.

## Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [PyPI](https://pypi.org/)
- [TestPyPI](https://test.pypi.org/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [Setuptools Documentation](https://setuptools.pypa.io/)
- [PEP 517](https://peps.python.org/pep-0517/) - Backend build system
- [PEP 518](https://peps.python.org/pep-0518/) - pyproject.toml specification
