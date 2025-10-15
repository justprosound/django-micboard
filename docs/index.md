# Django Micboard Documentation

**Professional wireless audio monitoring for Shure systems**

Django Micboard is a comprehensive Django reusable app for monitoring Shure wireless microphone systems via the Shure System API. It provides real-time monitoring, WebSocket updates, user assignments, and alerting capabilities.

## Features

- 🎤 **Real-time Monitoring** - Live updates via WebSocket for battery, RF levels, and audio
- 🔌 **Shure System API Integration** - Direct integration with Shure wireless receivers
- 👥 **User Assignments** - Assign devices to users with location tracking
- 🚨 **Smart Alerts** - Configurable notifications for battery, RF issues, and more
- 📊 **Dashboard Views** - Multiple view types (building, room, user, device type, priority)
- 🔒 **Rate Limiting** - Built-in API rate limiting and connection pooling
- 🐳 **Production Ready** - Django 4.2+/5+ compatible, fully tested

## Supported Devices

- UHF-R (Shure UHF-R series)
- QLX-D (Shure QLX-D series)
- ULX-D (Shure ULX-D series)
- Axient Digital (AD series)
- P10T (PSM1000)

## Quick Links

- [Quick Start Guide](quickstart.md) - Get up and running in minutes
- [Configuration](configuration.md) - All configuration options
- [API Reference](api-reference.md) - Complete API documentation
- [Architecture](architecture.md) - System design and components
- [Changelog](changelog.md) - Version history and updates

## Requirements

- Python 3.9+
- Django 4.2+
- Django Channels
- PostgreSQL (recommended) or SQLite
- Redis (for WebSocket support)

## Installation

```bash
pip install django-micboard
```

See the [Quick Start Guide](quickstart.md) for complete installation instructions.

## Support

- GitHub Issues: [github.com/justprosound/django-micboard/issues](https://github.com/justprosound/django-micboard/issues)
- Documentation: [django-micboard.readthedocs.io](https://django-micboard.readthedocs.io)

## License

Copyright (c) 2024-2025 Just ProSound LLC. All rights reserved.

See [LICENSE](../LICENSE) for full license text.
