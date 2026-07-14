# Django Micboard

> **Real-time wireless microphone monitoring for Django**

Django Micboard is a Django application for real-time monitoring and management of **Shure wireless microphone systems**. It provides a modern web interface for tracking microphone status, battery levels, RF signals, and audio levels across your wireless systems.

**Version**: 26.01.27 (CalVer: YY.MM.DD)
**License**: AGPL-3.0-or-later
**Python**: 3.13+
**Django**: 5.1 through 6.0

## Features

- 🎤 **Real-time Monitoring** - Live updates via WebSocket for battery, RF levels, and audio
- 🔌 **Shure System API Integration** - Full support for Shure wireless microphone systems
- 👥 **User Assignments** - Assign devices to users with location tracking
- 🚨 **Smart Alerts** - Configurable notifications for battery and RF issues
- 📊 **Admin Dashboard** - Visual oversight of devices and system health
- 🔒 **Rate Limiting** - Built-in API protection
- 🧪 **Pre-production Beta** - Django 5.1 through 6.0 compatible

## Quick Start

All installation and environment management uses [`uv`](https://github.com/astral-sh/uv).

```bash
# Add django-micboard to an existing uv-managed Django project
uv add "django-micboard[standard,tasks]"
```

```python
# Add to Django settings
INSTALLED_APPS = [
    # ... other apps
    "channels",
    "micboard",
]

# Configure Shure API
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://your-shure-system.local:10000",
    "SHURE_API_SHARED_KEY": "your-shared-secret",
}
```

```bash
# Run migrations
uv run --no-sync python manage.py migrate

# Start monitoring
uv run --no-sync python manage.py poll_devices
```


## Supported Systems

- **Shure UHF-R, QLX-D, ULX-D, Axient Digital (AD), PSM1000 series**
- **Plugin architecture** for additional manufacturers

## Documentation

- [Quick Start Guide](quickstart.md) - Get up and running quickly
- [Configuration](configuration.md) - All configuration options
- [Multitenancy](multitenancy.md) - Tenant-aware setup and behavior
- [Shure Integration](shure-integration.md) - Shure System API setup and usage
- [API Reference](api/endpoints.md) - REST and WebSocket endpoints
- [Architecture](development/architecture.md) - System design overview

## Requirements

- Python 3.13+
- Django 5.1 through 6.0
- Django Channels (for WebSocket support)
- Redis (recommended for production)

## Support

- GitHub Issues: [github.com/justprosound/django-micboard/issues](https://github.com/justprosound/django-micboard/issues)

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)

See [LICENSE](https://github.com/justprosound/django-micboard/blob/main/LICENSE) for full license text.
