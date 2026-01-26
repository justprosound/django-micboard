# django-micboard

Real-time multi-manufacturer wireless microphone monitoring for Django.

django-micboard provides a unified interface for monitoring wireless audio systems (Shure, Sennheiser, etc.) in real-time using Django Channels and manufacturer-specific APIs.

## Features

- **Multi-Manufacturer Support**: Plugin architecture for Shure System API, Sennheiser SSCv2, and more.
- **Real-Time Updates**: Live telemetry via WebSockets/SSE.
- **Device Lifecycle Management**: Automated discovery, tracking, and movement logging.
- **Regulatory Compliance**: Integrated frequency auditing against regulatory domains.
- **Alerting System**: User-specific notification preferences for battery, signal loss, and offline events.

## Requirements

- Python 3.9+
- Django 4.2+ / 5.0+
- Redis (required for production WebSockets)
- Manufacturer Middleware (e.g., Shure System API server)

## Local Setup

1. **Clone and Install**:
   ```bash
   git clone https://github.com/justprosound/django-micboard.git
   cd django-micboard
   pip install -e ".[dev,all]"
   ```

2. **Environment Configuration**:
   Create a `.env` file based on `.env.example`:
   ```bash
   cp .env.example .env
   ```

3. **Initialize Database**:
   *(For development only - do not run in production if database already exists)*
   ```bash
   python manage.py migrate
   ```

4. **Run Services**:
   ```bash
   # Terminal 1: Django server
   python manage.py runserver

   # Terminal 2: Device polling
   python manage.py poll_devices
   ```

## Running Tests

```bash
pytest
```

## Development

We use `ruff` for linting/formatting and `pre-commit` for git hooks.
```bash
pre-commit install
pre-commit run --all-files
```

## Deployment

Ensure `DEBUG=False` and all secrets are provided via environment variables. Do NOT manually edit migration files. Static files should be collected via `python manage.py collectstatic`.

## License

AGPL-3.0-or-later - see [LICENSE](LICENSE) for details.
