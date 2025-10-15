# django-micboard: A Reusable Django App for Shure Wireless Microphone Monitoring

> **⚠️ WORK IN PROGRESS**: This project is under active development and not yet ready for production use. Features, APIs, and documentation may change without notice. Use at your own risk.

`django-micboard` is a reusable Django application designed to provide comprehensive monitoring and management of Shure wireless microphone systems. Inspired by the original [micboard.io](https://micboard.io/) project, this app integrates with the **Shure System API** (typically hosted locally on a Windows system) to offer a modern, maintainable, and extensible solution for real-time device communication and data visualization.

## Documentation

Complete documentation is available in the `docs/` directory:

- **[Quick Start Guide](docs/quickstart.md)** - Get up and running quickly
- **[Configuration Guide](docs/configuration.md)** - Detailed configuration options
- **[API Reference](docs/api-reference.md)** - Complete REST and WebSocket API documentation
- **[Architecture Overview](docs/architecture.md)** - System design and data flow
- **[Developer Guide](docs/development.md)** - Contributing and extending the app
- **[User Assignments](docs/user-assignments.md)** - Managing device assignments
- **[Rate Limiting](docs/rate-limiting.md)** - API rate limiting configuration
- **[Changelog](docs/changelog.md)** - Version history and updates

To build the documentation locally:

```bash
pip install -r docs/requirements.txt
mkdocs serve
```

Then visit http://127.0.0.1:8000 in your browser.

## Architecture

This app uses a **middleware-based architecture**:

- **Shure System API Server**: Installed middleware that handles all communication with Shure devices via official APIs
- **Django App**: Web interface that consumes the Shure System API for data display and real-time updates
- **WebSocket Layer**: Real-time updates via Django Channels for live device monitoring
- **Background Polling**: Management command that polls the API and broadcasts updates

## Requirements

- Python 3.8+
- Django 4.2+
- Shure System API server (installed separately)
- Redis (recommended for production WebSocket support)

## Installation

### Option 1: Install from PyPI (Recommended)

```bash
# Basic installation
pip install django-micboard

# With Redis support (recommended for production)
pip install django-micboard[redis]

# With development tools
pip install django-micboard[dev]
```

### Option 2: Install from GitHub

```bash
# Latest from main branch
pip install git+https://github.com/justprosound/django-micboard.git

# Specific version tag
pip install git+https://github.com/justprosound/django-micboard.git@v25.10.14
```

### Option 3: Install from Source

```bash
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard
pip install -e .  # Editable install for development
```

## Setup

### 1. Install Shure System API Server

1. Download and install the Shure System API from the [Shure System API product page](https://www.shure.com/en-US/products/software/systemapi)
2. Install it on a computer connected to your Shure device network
3. Configure TLS certificates if accessing remotely (see Shure documentation)
4. Start the System API server and note the URL (e.g., `http://localhost:8080`)

 Static assets include app icons under `micboard/static/micboard/`. Splash screens have been removed.

1. Add 'micboard' to `INSTALLED_APPS` in your Django settings:
   ```python
   INSTALLED_APPS = [
       # ... other apps
       'channels',
       'micboard',
   ]
   ```

2. Configure the Shure System API connection in your settings:
   ```python
   MICBOARD_CONFIG = {
       'SHURE_API_BASE_URL': 'http://localhost:8080',
       'SHURE_API_USERNAME': None,  # If authentication required
       'SHURE_API_PASSWORD': None,  # If authentication required
       'SHURE_API_TIMEOUT': 10,
       'SHURE_API_VERIFY_SSL': True,

       # Retry and rate limiting
       'SHURE_API_MAX_RETRIES': 3,
       'SHURE_API_RETRY_BACKOFF': 0.5,
       'SHURE_API_RETRY_STATUS_CODES': [429, 500, 502, 503, 504],
   }
   ```

   See [docs/configuration.md](docs/configuration.md) for complete configuration options.

3. Configure Channels for WebSocket support in your settings:
   ```python
   ASGI_APPLICATION = 'your_project.asgi.application'

   CHANNEL_LAYERS = {
       'default': {
           'BACKEND': 'channels.layers.InMemoryChannelLayer'
           # For production, use Redis
       },
   }
   ```

4. Update your `asgi.py` file:
   ```python
   from channels.routing import ProtocolTypeRouter, URLRouter
   from channels.auth import AuthMiddlewareStack
   from django.core.asgi import get_asgi_application
   from micboard.routing import websocket_urlpatterns

   application = ProtocolTypeRouter({
       "http": get_asgi_application(),
       "websocket": AuthMiddlewareStack(
           URLRouter(websocket_urlpatterns)
       ),
   })
   ```

5. Include the URLs in your main `urls.py`:
   ```python
   from django.urls import include, path

   urlpatterns = [
       path('micboard/', include('micboard.urls')),
   ]
   ```

4. **Run migrations**:
   ```bash
   # Create migrations for micboard app
   python manage.py makemigrations micboard

   # Apply migrations
   python manage.py migrate
   ```

7. Collect static files:
   ```bash
   python manage.py collectstatic
   ```

## Usage

### Starting the Polling Service

The polling service fetches data from the Shure System API and broadcasts updates:

```bash
python manage.py poll_devices
```

Options:
- `--interval SECONDS`: Polling interval (default: 10 seconds)
- `--no-broadcast`: Disable WebSocket broadcasting

For production, run as a background service using systemd, supervisor, or similar.

### Running the Development Server

For WebSocket support, use Daphne instead of the standard Django server:

```bash
daphne -b 0.0.0.0 -p 8000 your_project.asgi:application
```

Or for development:
```bash
python manage.py runserver
```

## API Endpoints

### Rate Limiting

All API endpoints are rate-limited to prevent abuse:

- **`/api/data/`**: 120 requests/minute (2 req/sec)
- **`/api/discover/`**: 5 requests/minute (discovery is expensive)
- **`/api/refresh/`**: 10 requests/minute
- **`/api/config/`**: 60 requests/minute (default)
- **`/api/group/`**: 60 requests/minute (default)

Rate limit responses return HTTP 429 with `Retry-After` header.

### Endpoints

- **`GET /`** - Main dashboard
- `GET /micboard/api/data/` - Get current device data (JSON)
- `POST /micboard/api/discover/` - Trigger device discovery
- `POST /micboard/api/refresh/` - Force refresh device data
- `POST /micboard/api/slot/` - Update slot configuration
- `POST /micboard/api/config/` - Update configuration
- `POST /micboard/api/group/` - Update group settings

### New Views

The app now includes several new views to filter and display devices:

- **Devices by Type**: `/micboard/device-type/<device_type>/` (e.g., `/micboard/device-type/uhfr/`)
- **Devices by Building**: `/micboard/building/<building_name>/` (e.g., `/micboard/building/Building%20A/`)
- **Devices by User**: `/micboard/user/<username>/` (e.g., `/micboard/user/admin/`)
- **Devices by Room**: `/micboard/room/<room_name>/` (e.g., `/micboard/room/Room%20101/`)
- **Devices by Priority**: `/micboard/priority/<priority>/` (e.g., `/micboard/priority/high/`)

These views are also accessible via dropdown menus in the main dashboard navigation.

### WebSocket Connection

Connect to: `ws://your-server/micboard/ws`

The WebSocket will receive real-time updates with device data.

## Configuration

### Device Management

Devices are automatically discovered and created via the Shure System API. You can manage them through:

1. **Django Admin**: Go to `/admin/micboard/device/`
2. **API Discovery**: POST to `/micboard/api/discover/`

### Groups

Create groups in Django Admin to organize devices into logical collections.

## Dependencies

### Python Dependencies

Python dependencies are managed using `pip-tools` and `pyproject.toml`. See [docs/dependency-management.md](docs/dependency-management.md) for details on how to update and manage Python dependencies.

### Frontend Dependencies

Frontend dependencies (Bootstrap, Sass, IBM Plex font) are managed using `npm`. Refer to the "Frontend Development" section under "Development" for instructions on installing and building these assets.

## Development

### Project Structure

```
micboard/
├── management/
│   └── commands/
│       └── poll_devices.py       # Background polling command
├── migrations/                    # Database migrations
├── static/micboard/              # Static assets (JS, CSS, images)
├── templates/micboard/           # Django templates
├── admin.py                      # Django admin configuration
├── apps.py                       # App configuration
├── consumers.py                  # WebSocket consumers
├── models.py                     # Database models
├── routing.py                    # WebSocket routing
├── shure_api_client.py          # Shure System API client
├── urls.py                      # URL configuration
└── views.py                     # View functions
```

### Frontend Development

This project uses `npm` to manage frontend dependencies and build static assets.

1.  **Install Node.js dependencies**:
    ```bash
    npm install
    ```

2.  **Build static assets**:
    ```bash
    npm run build
    ```

### Python Dependency Management

Python dependencies are managed using `pip-tools` and `pyproject.toml`. See [docs/dependency-management.md](docs/dependency-management.md) for details on how to update and manage Python dependencies.

### Testing

```bash
python manage.py test micboard
```

## Troubleshooting

### API Connection Issues

1. Verify Shure System API server is running
2. Check `SHURE_API_BASE_URL` in settings
3. Test API connection:
   ```bash
   curl http://localhost:8080/api/v1/devices
   ```

### WebSocket Issues

1. Ensure Channels is properly configured
2. For production, use Redis channel layer instead of in-memory
3. Check that Daphne is running (not standard Django server)

### No Device Data

1. Ensure devices are powered on and connected to network
2. Trigger discovery: POST to `/micboard/api/discover/`
3. Check polling service logs: look for errors in `micboard.log`
4. Verify Shure System API can see devices

## Production Deployment

### Using systemd for Polling Service

Create `/etc/systemd/system/micboard-poll.service`:

```ini
[Unit]
Description=Micboard Device Polling Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/your/project
ExecStart=/path/to/venv/bin/python manage.py poll_devices --interval 10
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable micboard-poll
sudo systemctl start micboard-poll
```

### Using systemd for Daphne

Create `/etc/systemd/system/daphne.service`:

```ini
[Unit]
Description=Daphne ASGI Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/your/project
ExecStart=/path/to/venv/bin/daphne -b 0.0.0.0 -p 8000 your_project.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

## Notes

- This app replaces direct device communication with API-based communication
- All device polling is handled by the Shure System API middleware
- WebSocket support requires Channels and an ASGI server (Daphne)
- For production, use Redis for the Channels layer
- Original static files and UI are preserved from the micboard project

## License

Based on the original micboard project. Check the original repository for licensing information.

## Support

For Shure System API issues, consult the [official Shure documentation](https://www.shure.com/en-US/products/software/systemapi).

For Django app issues, check the logs and ensure all configuration is correct.
