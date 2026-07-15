# Installation Guide

> All environments and dependencies must be managed with [`uv`](https://github.com/astral-sh/uv).

Complete installation instructions for django-micboard.

## System Requirements

### Minimum Requirements

- **Python**: 3.13 or higher
- **Django**: 5.1 through 6.0
- **Database**: PostgreSQL for production; SQLite for local development and tests
- **Memory**: 512MB RAM minimum
- **Storage**: 100MB free space

### Recommended Setup

- **Python**: 3.13+
- **Database**: PostgreSQL 13+
- **Redis**: 6.0+ (for native Huey and WebSocket support)
- **Memory**: 1GB+ RAM
- **Web Server**: Nginx + Gunicorn or Apache + mod_wsgi

## Installation Methods

### Method 1: Add to a Host Project

```bash
# Add the package and common integrations to the host project's lockfile
uv add "django-micboard[standard,realtime]"

# Or for latest development version
uv add "django-micboard @ git+https://github.com/justprosound/django-micboard.git"
```


### Method 2: From Source with UV (RECOMMENDED)

```bash
# Clone repository
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard

# Install the project and every supported optional integration
uv sync --locked --all-extras

# To install optional extras only
uv sync --locked --extra realtime --extra tasks --extra standard
```

### Method 3: Docker Installation

> **NOTE:** Any Dockerfile or base container for django-micboard MUST use `uv` for all installation steps. All sample Dockerfiles below demonstrate this policy.

```yaml
# docker-compose.yml
version: '3.8'
services:
  micboard:
    image: django-micboard:latest
    environment:
      - DJANGO_SETTINGS_MODULE=myproject.settings
      - DATABASE_URL=postgresql://user:pass@db:5432/micboard
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis

  db:
    image: postgres:13
    environment:
      - POSTGRES_DB=micboard
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass

  redis:
    image: redis:6-alpine
```

## Django Configuration

### Basic Setup

Add to your Django `settings.py`. Keep Django's built-in `SecurityMiddleware` enabled and
configure any Content Security Policy in the host project; Micboard does not replace host
security headers.

```python
# settings.py
import os

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

INSTALLED_APPS = [
    # Django core apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'channels',
    'huey.contrib.djhuey',

    # Micboard
    'micboard',
]

# Database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'micboard',
        'USER': 'micboard_user',
        'PASSWORD': 'secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Native Huey Django integration. Use immediate mode only for local development/tests.
HUEY = {
    "huey_class": "huey.RedisHuey",
    "name": "micboard",
    "connection": {
        "url": os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
    },
    "immediate": DEBUG,
}

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = '/var/www/micboard/static/'

# Media files (optional)
MEDIA_URL = 'media/'
MEDIA_ROOT = '/var/www/micboard/media/'
```

### Shure API Configuration

```python
import os

# Shure System API settings use the shared key issued by Shure System API.
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": os.environ.get(
        "MICBOARD_SHURE_API_BASE_URL", "https://your-shure-system.local:10000"
    ),
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
    "SHURE_API_TIMEOUT": int(os.environ.get("MICBOARD_SHURE_API_TIMEOUT", "30")),
}

# Exact hostnames that credential-bearing Manufacturer API Server checks may contact.
# Do not include schemes, ports, paths, or wildcards.
MICBOARD_API_SERVER_ALLOWED_HOSTS = ["your-shure-system.local"]
```

The package reads Django settings rather than environment variables directly. Host projects may
use different environment names, but must map values into `MICBOARD_CONFIG` themselves.
The API-server allowlist is enforced for admin connection checks so an editable URL cannot send a
manufacturer credential to an arbitrary destination.

### Channels Configuration (WebSocket)

```python
# ASGI application
ASGI_APPLICATION = 'myproject.asgi.application'

# Channel layers for WebSocket support
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}
```

### Security Settings

```python
# Security settings
SECRET_KEY = 'your-very-secure-secret-key-here'
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']

# HTTPS settings (recommended for production)
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Session security
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

### Optional Features

```python
# Standard Django email configuration for host-project notifications
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/micboard/django.log',
        },
    },
    'loggers': {
        'micboard': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

## ASGI Configuration

Update your `asgi.py`:

```python
# asgi.py
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django_asgi_app = get_asgi_application()

# Import micboard WebSocket routes
from micboard.websockets.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
```

## Database Setup

### PostgreSQL (Required for Production)

PostgreSQL is required when `DEBUG=False`. django-micboard's deployment system check rejects
other database engines in production because cross-model IP ownership relies on PostgreSQL
transaction advisory locks. SQLite remains supported for local development and tests.

```bash
# Create database and user
sudo -u postgres psql
```

```sql
CREATE DATABASE micboard;
CREATE USER micboard_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE micboard TO micboard_user;
ALTER USER micboard_user CREATEDB;
\q
```

### SQLite (Development Only)

```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

## Initial Setup

### Run Migrations

```bash
# Apply database migrations
uv run --no-sync python manage.py migrate

# Create superuser
uv run --no-sync python manage.py createsuperuser
```

### Collect Static Files

```bash
# Collect static files for production
uv run --no-sync python manage.py collectstatic --noinput
```

### Verify Installation

```bash
# Run the package test suite from a source checkout
uv run --no-sync pytest

# Check system health
uv run --no-sync python manage.py check

# Test Shure API connection (if configured)
uv run --no-sync python manage.py diagnostic_api_health_check
```

## Production Deployment

### Gunicorn + Nginx

**Install dependencies:**
```bash
uv add gunicorn
sudo apt install nginx
```
**Gunicorn configuration:**
```bash
# Create systemd service
sudo nano /etc/systemd/system/micboard.service
```

```ini
[Unit]
Description=Micboard Django Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/micboard
Environment="DJANGO_SETTINGS_MODULE=myproject.settings"
ExecStart=/usr/local/bin/uv run --no-sync gunicorn --workers 3 --bind unix:/var/www/micboard/micboard.sock myproject.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

> **NOTE:** All virtual environments in this project must be created with `uv`. Set
> `ExecStart` to the absolute path returned by `command -v uv` on the deployment host.

**Nginx configuration:**
```nginx
# /etc/nginx/sites-available/micboard
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /var/www/micboard/static/;
    }

    location /media/ {
        alias /var/www/micboard/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/micboard/micboard.sock;
    }

    # WebSocket support
    location = /ws {
        proxy_pass http://unix:/var/www/micboard/micboard.sock;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable site and restart services:**
```bash
sudo ln -s /etc/nginx/sites-available/micboard /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable micboard
sudo systemctl start micboard
```

### Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

RUN uv run --no-sync python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "gunicorn", "--bind", "0.0.0.0:8000", "myproject.wsgi:application"]
```

> **NOTE:** The image copies a pinned binary from Astral's official uv image and installs the locked project with `uv sync`.

**Build and run:**
```bash
docker build -t micboard .
docker run -p 8000:8000 micboard
```

## Post-Installation Setup

### Device Discovery

```bash
# Expand CIDRs already configured in the admin discovery settings
uv run --no-sync python manage.py sync_discovery --manufacturer shure --scan-cidrs

# Or add specific devices
uv run --no-sync python manage.py discovery_add_devices --ips 192.168.1.100,192.168.1.101
```

### Start Monitoring

```bash
# Initial device poll
uv run --no-sync python manage.py poll_devices --manufacturer shure

# Enqueue one poll through native Huey
uv run --no-sync python manage.py poll_devices --manufacturer shure --async
```

### Admin Configuration

1. Access `/admin/` with superuser credentials
2. Configure user permissions
3. Set up device assignments
4. Configure alert thresholds

## Troubleshooting Installation

### Import Errors

**Module not found:**
```bash
# Ensure the lockfile and environment are synchronized
uv sync --locked --all-extras

# Check Python path
uv run --no-sync python -c "import micboard; print(micboard.__file__)"
```

> Use `uv sync` with the project lockfile. Do not install this project from ad hoc requirement files.
### Database Errors

**Migration failures:**
```bash
# Inspect migration state without rewriting migration history
uv run --no-sync python manage.py showmigrations micboard
uv run --no-sync python manage.py migrate --plan

# Check database connectivity
uv run --no-sync python manage.py dbshell
```

### Permission Errors

**Static file issues:**
```bash
# Fix permissions
sudo chown -R www-data:www-data /var/www/micboard/
sudo chmod -R 755 /var/www/micboard/
```

### WebSocket Issues

**Connection failures:**
```bash
# Check Redis connectivity
redis-cli ping

# Verify ASGI configuration
uv run --no-sync python manage.py check
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Get monitoring quickly
- [Configuration](configuration.md) - Detailed configuration options
- [Shure Integration](shure-integration.md) - Shure System API setup
- [Admin Interface](guides/admin-interface.md) - Using the admin dashboard
