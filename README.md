# django-micboard

> **⚠️ ACTIVE DEVELOPMENT**: This project is under active development and not yet ready for production use. Features, APIs, and documentation may change without notice.

A community-driven open source Django app for real-time monitoring and management of wireless microphone systems. Integrates with external Shure System API middleware for device communication.

## Version: 25.10.15

This project uses [Calendar Versioning](https://calver.org/) (YY.MM.DD) for easier tracking of changes against releases.

[![PyPI Version](https://img.shields.io/pypi/v/django-micboard)](https://pypi.org/project/django-micboard/)
[![Build Status](https://github.com/justprosound/django-micboard/actions/workflows/ci.yml/badge.svg)](https://github.com/justprosound/django-micboard/actions)
[![Coverage Status](https://coveralls.io/repos/github/justprosound/django-micboard/badge.svg?branch=main)](https://coveralls.io/github/justprosound/django-micboard?branch=main)
[![Documentation Status](https://readthedocs.org/projects/django-micboard/badge/?version=latest)](https://django-micboard.readthedocs.io/en/latest/?badge=latest)

## Architecture

```
Shure Devices → Shure System API (external) → ShureSystemAPIClient → poll_devices → Models → WebSocket
```

- **Shure System API**: External middleware handling device communication
- **ShureSystemAPIClient**: HTTP client in `micboard/shure/client.py`
- **poll_devices**: Management command that polls API, updates models, broadcasts via Channels
- **WebSocket**: Real-time updates to frontend via Django Channels

## Requirements

- Python 3.9+
- Django 4.2+/5.0+
- Shure System API server (installed separately)
- Redis (recommended for production WebSocket support)

## Installation

### Option 1: Install from PyPI (When Available)

```bash
pip install django-micboard
# Or with Redis support
pip install django-micboard[redis]
```

### Option 2: Install from Source (Development)

```bash
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard
pip install -e .  # Editable install
```

## Quick Start

See [docs/quickstart.md](docs/quickstart.md) for detailed setup instructions.

### Minimal Setup

1. Add to `INSTALLED_APPS`:
```python
INSTALLED_APPS = [
    # ... other apps
    'channels',
    'micboard',
]
```

2. Configure Shure System API connection:
```python
MICBOARD_CONFIG = {
    'SHURE_API_BASE_URL': 'http://localhost:10000',  # or https:// for SSL
    'SHURE_API_SHARED_KEY': 'your-shared-secret-here',  # Required: from Shure System API
    'SHURE_API_VERIFY_SSL': True,  # Set to False only for self-signed certificates
}
```

3. Configure Channels:
```python
ASGI_APPLICATION = 'your_project.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    },
}
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Start services:
```bash
# Terminal 1: Django/Daphne
daphne -b 0.0.0.0 -p 8000 your_project.asgi:application

# Terminal 2: Device polling (required)
python manage.py poll_devices
```

## Documentation

- [Quick Start Guide](docs/quickstart.md)
- [Architecture Overview](docs/architecture.md)
- [Configuration Guide](docs/configuration.md)
- [Rate Limiting](docs/rate-limiting.md)
- [API Reference](docs/api-reference.md)
- [User Assignments](docs/user-assignments.md)
- [Dependency Management](docs/dependency-management.md)
- [Changelog](docs/changelog.md)

## Testing

```bash
pytest tests/ -v  # 60 tests
```

## Contributing

This is a community-driven open source project. Contributions welcome!

1. Follow existing code patterns
2. Add type hints and docstrings
3. Use keyword-only parameters for optional args
4. Run tests before submitting: `pytest tests/ -v`
5. Update documentation as needed

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

AGPL-3.0-or-later

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

See [LICENSE](LICENSE) for full text.

## Support

- **Issues**: Open an issue on GitHub
- **Shure System API**: Consult [Shure API Documentation](https://shure.stoplight.io)
- **Django Channels**: See [Channels Documentation](https://channels.readthedocs.io/)
