# Installation Guide

Complete installation instructions for django-micboard.

## System Requirements

### Minimum Requirements

- **Python**: 3.9 or higher
- **Django**: 4.2 or higher (5.0+ recommended)
- **Database**: PostgreSQL, MySQL, or SQLite
- **Memory**: 512MB RAM minimum
- **Storage**: 100MB free space

### Recommended Setup

- **Python**: 3.11+
- **Database**: PostgreSQL 13+
- **Redis**: 6.0+ (for WebSocket support)
- **Memory**: 1GB+ RAM
- **Web Server**: Nginx + Gunicorn or Apache + mod_wsgi

## Installation Methods

### Method 1: pip Install (Recommended)

```bash
# Install from PyPI
pip install django-micboard

# Or for latest development version
pip install git+https://github.com/justprosound/django-micboard.git
```

### Method 2: From Source

```bash
# Clone repository
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard

# Install in development mode
pip install -e .

# Install optional dependencies
pip install django-micboard[channels,tasks,observability]
```

### Method 3: Docker Installation

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

Add to your Django `settings.py`:

```python
# settings.py
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
# Shure System API settings
MICBOARD_SHURE_API = {
    'BASE_URL': 'https://your-shure-system.local',
    'USERNAME': 'api_user',
    'PASSWORD': 'secure_password',
    'VERIFY_SSL': True,
    'TIMEOUT': 30,
}

# Optional: Additional manufacturers
# MICBOARD_SENNHEISER_API = {
#     'BASE_URL': 'https://sennheiser-system.local',
#     'USERNAME': 'api_user',
#     'PASSWORD': 'secure_password',
# }
```

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
# Rate limiting
MICBOARD_RATE_LIMITS = {
    'api_calls': '1000/hour',
    'device_polling': '60/minute',
}

# Email alerts (optional)
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
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

# Import micboard WebSocket routes
from micboard.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': URLRouter(websocket_urlpatterns),
})
```

## Database Setup

### PostgreSQL (Recommended)

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
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### Collect Static Files

```bash
# Collect static files for production
python manage.py collectstatic --noinput
```

### Verify Installation

```bash
# Run tests
python manage.py test micboard

# Check system health
python manage.py check

# Test Shure API connection (if configured)
python manage.py shell -c "
from micboard.integrations.shure.client import ShureSystemAPIClient
client = ShureSystemAPIClient()
print('API Health:', client.check_health())
"
```

## Production Deployment

### Gunicorn + Nginx

**Install dependencies:**
```bash
pip install gunicorn
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
Environment="PATH=/var/www/micboard/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=myproject.settings"
ExecStart=/var/www/micboard/venv/bin/gunicorn --workers 3 --bind unix:/var/www/micboard/micboard.sock myproject.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

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
    location /ws/ {
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
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "myproject.asgi:application"]
```

**Build and run:**
```bash
docker build -t micboard .
docker run -p 8000:8000 micboard
```

## Post-Installation Setup

### Device Discovery

```bash
# Add IP ranges for device discovery
python manage.py add_shure_devices --cidr 192.168.1.0/24

# Or add specific devices
python manage.py add_shure_devices --ips 192.168.1.100 192.168.1.101
```

### Start Monitoring

```bash
# Initial device poll
python manage.py poll_devices --manufacturer shure

# Start continuous monitoring
python manage.py poll_devices --manufacturer shure --continuous
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
# Ensure all dependencies are installed
pip install -r requirements.txt

# Check Python path
python -c "import micboard; print(micboard.__file__)"
```

### Database Errors

**Migration failures:**
```bash
# Reset migrations (development only)
python manage.py migrate --run-syncdb

# Check database connectivity
python manage.py dbshell
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
python manage.py check
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Get monitoring quickly
- [Configuration](configuration.md) - Detailed configuration options
- [Shure Integration](shure-integration.md) - Shure System API setup
- [Admin Interface](guides/admin-interface.md) - Using the admin dashboard
