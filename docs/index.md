---
title: "Django Micboard"
type: explanation
audience: both
---
> **Real-time wireless microphone monitoring for Django**

django-micboard is a reusable Django app for real-time monitoring and management of wireless microphone and RF systems from several manufacturers. It tracks device status, battery levels, RF signals and audio levels across your wireless systems.

**License**: AGPL-3.0-or-later
**Python**: 3.14+
**Django**: 5.2 through 6.0

## Features

- **Real-time monitoring**: battery, RF and audio levels, polled over HTTP with optional WebSocket push
- **Manufacturer integrations**: Shure System API and Sennheiser SSCv2, with a plugin contract for more
- **Performer assignments**: tie wireless units to performers and monitoring groups
- **Alerts**: battery, signal, audio and offline conditions
- **Admin and dashboards**: Django admin plus tenant-aware dashboards and kiosk walls
- **Multi-tenancy**: optional site, organization and campus isolation
- **Transport hardening**: TLS-only, authenticated manufacturer connections

## Get started

Add the package to an existing uv-managed Django project with `uv add "django-micboard[standard,realtime,shure]"`, then follow the [Quick start](quickstart.md).

## Supported systems

Shure (System API) and Sennheiser (SSCv2) integrations ship today. Other manufacturers are added as plugins ([Manufacturer plugin development](plugin-development.md)).

## Documentation

The documentation is organized by what you need:

- **Tutorials** teach by doing: start with the [Quick start](quickstart.md).
- **How-to guides** solve a specific task, such as [Installation](installation.md), [Enable multi-tenancy](multitenancy-setup.md) or [Shure integration](shure-integration.md).
- **Reference** states facts: [Configuration](configuration.md), [HTTP endpoints](api/endpoints.md) and the [generated Python API](api/models.md).
- **Explanation** covers the why: [Architecture](architecture.md), [Multi-tenancy](multitenancy.md) and the architecture decisions.

## Requirements

- Python 3.14+
- Django 5.2 through 6.0
- Django Channels (for WebSocket support)
- Redis (recommended for production)

## Support

- GitHub Issues: [github.com/justprosound/django-micboard/issues](https://github.com/justprosound/django-micboard/issues)

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)

See [LICENSE](https://github.com/justprosound/django-micboard/blob/main/LICENSE) for full license text.
