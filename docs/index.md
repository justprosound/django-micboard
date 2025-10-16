# Django Micboard

> **⚠️ ACTIVE DEVELOPMENT**: This project is under active development and has not been released. APIs and features are subject to change.

Welcome to the django-micboard documentation!

django-micboard is a Django application for real-time monitoring and management of **multi-manufacturer wireless microphone systems**. It uses a **plugin architecture** to support different wireless microphone manufacturers, providing a modern web interface for monitoring microphone status, battery levels, RF signals, and audio levels across your wireless systems.

**Version**: 25.10.15 (CalVer: YY.MM.DD)
**License**: AGPL-3.0-or-later
**Community**: Open source, community-driven project

## Features

- 🎤 **Real-time Monitoring** - Live updates via WebSocket for battery, RF levels, and audio
- 🔌 **Multi-Manufacturer Support** - Plugin architecture supporting Shure, Sennheiser, and other manufacturers
- 👥 **User Assignments** - Assign devices to users with location tracking
- 🚨 **Smart Alerts** - Configurable notifications for battery, RF issues, and more
- 📊 **Dashboard Views** - Multiple view types (building, room, user, device type, priority)
- 🔒 **Rate Limiting** - Built-in API rate limiting and connection pooling
- 🐳 **Production Ready** - Django 4.2+/5.0+ compatible, fully tested

## Supported Manufacturers

- **Shure** - UHF-R, QLX-D, ULX-D, Axient Digital (AD), PSM1000 series
- **Extensible** - Plugin architecture for adding new manufacturers

## Quick Links

- [Quick Start Guide](quickstart.md) - Get up and running quickly
- [Configuration](configuration.md) - All configuration options
- [Plugin Development](plugin-development.md) - Add support for new manufacturers
- [API Reference](api-reference.md) - Complete API documentation
- [Architecture](architecture.md) - System design and components
- [Changelog](changelog.md) - Version history

## Requirements

- Python 3.9+
- Django 4.2+ or 5.0+
- Django Channels
- Redis (for WebSocket support)

## Installation

```bash
pip install django-micboard
```

See the [Quick Start Guide](quickstart.md) for complete installation instructions.

## Support

- GitHub Issues: [github.com/justprosound/django-micboard/issues](https://github.com/justprosound/django-micboard/issues)

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)

See [LICENSE](../LICENSE) for full license text.
