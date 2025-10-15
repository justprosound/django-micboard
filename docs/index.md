# Django Micboard

> **⚠️ ACTIVE DEVELOPMENT**: This project is under active development and has not been released. APIs and features are subject to change.

Welcome to the django-micboard documentation!

django-micboard is a Django application for real-time monitoring and management of Shure wireless microphone systems. It integrates with the **Shure System API** to provide a modern web interface for monitoring microphone status, battery levels, RF signals, and audio levels across your wireless systems.

**Version**: 25.10.15 (CalVer: YY.MM.DD)
**License**: AGPL-3.0-or-later
**Community**: Open source, community-driven project

## Features

- 🎤 **Real-time Monitoring** - Live updates via WebSocket for battery, RF levels, and audio
- 🔌 **Shure System API Integration** - Integration with Shure wireless receivers
- 👥 **User Assignments** - Assign devices to users with location tracking
- 🚨 **Smart Alerts** - Configurable notifications for battery, RF issues, and more
- 📊 **Dashboard Views** - Multiple view types (building, room, user, device type, priority)
- 🔒 **Rate Limiting** - Built-in API rate limiting and connection pooling
- 🐳 **Production Ready** - Django 4.2+/5.0+ compatible, fully tested

## Supported Devices

- UHF-R (Shure UHF-R series)
- QLX-D (Shure QLX-D series)
- ULX-D (Shure ULX-D series)
- Axient Digital (AD series)
- P10T (PSM1000)

## Quick Links

- [Quick Start Guide](quickstart.md) - Get up and running quickly
- [Configuration](configuration.md) - All configuration options
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
