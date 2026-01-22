# Django Micboard - Configuration Guide

This guide covers secure configuration for both development and production environments.

**⚠️ IMPORTANT: Never commit `.env.local` or any files containing real credentials to the repository.**

## Quick Start

1. Copy the environment template:
   ```bash
   cp .env.example .env.local
   ```

2. Edit `.env.local` with your values:
   ```bash
   vim .env.local
   ```

3. Load environment variables before running:
   ```bash
   # For bash
   source .env.local
   
   # Or use python-dotenv
   python manage.py runserver
   ```

## Environment Configuration

### Django Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_ENV` | `development` | Environment: development, staging, or production |
| `DJANGO_SECRET_KEY` | (required) | Secret key for Django; generate with `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DEBUG` | `True` | Enable debug mode (NEVER True in production!) |
| `DATABASE_ENGINE` | `django.db.backends.sqlite3` | Database backend |
| `DATABASE_NAME` | `db.sqlite3` | Database file path or name |

### Shure Integration

Configure connection to the Shure System API:

| Variable | Default | Description |
|----------|---------|-------------|
| `SHURE_API_BASE_URL` | `http://localhost:8000` | Base URL of local Shure System API |
| `SHURE_API_TIMEOUT` | `10` | Request timeout in seconds |
| `SHURE_API_RATE_LIMIT` | `120` | Rate limit in requests per minute |

### VPN Device Population

For connecting to live Shure devices on your VPN:

| Variable | Example | Description |
|----------|---------|-------------|
| `SHURE_DEVICE_IPS` | `172.21.1.100,172.21.1.101` | Comma-separated list of device IPs |
| `SHURE_DEVICE_DISCOVERY_TIMEOUT` | `5` | Discovery timeout in seconds |
| `SHURE_DEVICE_VERIFY_SSL` | `false` | Whether to verify SSL for device connections |

## Local Development Setup

### 1. Initial Setup

```bash
# Navigate to project root
cd /path/to/django-micboard

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env.local

# Run migrations
python manage.py migrate
```

### 2. Create Local Shure System API

The local Shure System API is needed for testing without connecting to real devices:

```bash
# Start local Shure API (requires Java runtime)
# See demo/docker/README.md for Docker setup

# Or configure via Docker Compose
docker compose -f demo/docker/docker-compose.yml up -d
```

### 3. Configure Device IPs (Optional)

To populate the local API with real VPN devices:

```bash
# Edit .env.local
export SHURE_DEVICE_IPS="172.21.1.100,172.21.1.101,172.21.1.102"

# Run discovery
python scripts/device_discovery.py discover --env
```

### 4. Run Development Server

```bash
# Load environment
source .env.local

# Start Django with Channels
python manage.py runserver 0.0.0.0:8000
```

## VPN Device Population

### Overview

When you have access to a VPN with live Shure devices, you can populate the local development environment:

```
VPN Devices (172.21.x.x)
    ↓
device_discovery.py (probes devices)
    ↓
device_manifest.json (discovered device list - NOT committed)
    ↓
Local Shure System API (updated with device info)
    ↓
Django Micboard (polls and displays devices)
```

### Step-by-Step

1. **Set device IPs** in `.env.local`:
   ```bash
   SHURE_DEVICE_IPS=172.21.1.100,172.21.1.101,172.21.1.102
   ```

2. **Run discovery**:
   ```bash
   python scripts/device_discovery.py discover --env
   ```
   
   This probes devices and saves `device_manifest.json` (local only, not committed).

3. **Populate local API** (when implemented):
   ```bash
   python scripts/device_discovery.py populate
   ```

4. **Verify in Django admin**:
   ```
   http://localhost:8000/admin/micboard/manufacturer/
   ```

### Files Generated During Population

These files are intentionally **NOT committed** (see `.gitignore`):

- `device_manifest.json` - List of discovered devices
- `device_discovery_local.py` - Any local discovery scripts
- `.env.local` - Your actual secrets

## Security Best Practices

### 1. Never Commit Secrets

```bash
# ❌ WRONG - Will leak credentials
export SHURE_SHARED_KEY="abc123"
git add .

# ✅ RIGHT - Keep in .env.local (in .gitignore)
echo 'SHURE_SHARED_KEY=abc123' >> .env.local
```

### 2. Use Environment Variables

```python
# ❌ WRONG - Hardcoded secret
SHURE_API_KEY = "your-key-here"

# ✅ RIGHT - Load from environment
import os
SHURE_API_KEY = os.environ.get('SHURE_API_KEY')
```

### 3. Keep .env.example Safe

The `.env.example` file is committed and shows all variables, but with no real values:

```bash
# ✅ OK to commit
cp .env.example .env.example
git add .env.example

# ❌ NEVER commit
git add .env.local
git add config/secrets.yml
git add .env.production
```

### 4. Staging & Production

For staging/production environments:

```bash
# Use secure secret management
docker run \
  -e DJANGO_SECRET_KEY="$(aws secretsmanager get-secret-value ...)" \
  -e SHURE_DEVICE_IPS="$PROD_DEVICE_IPS" \
  micboard:latest
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'micboard'"

Make sure to install in development mode:

```bash
pip install -e .
```

### "Connection refused" on Shure API

Verify the local Shure System API is running:

```bash
# Check if Docker container is running
docker ps | grep shure

# Or check port 8000
curl http://localhost:8000/api/health
```

### Device Discovery Finds No Devices

1. Verify VPN connection:
   ```bash
   ping 172.21.1.100  # Replace with actual device IP
   ```

2. Check `SHURE_DEVICE_IPS` is set:
   ```bash
   echo $SHURE_DEVICE_IPS
   ```

3. Test individual device:
   ```bash
   python scripts/device_discovery.py test --ip 172.21.1.100
   ```

## Reference

- [Django Settings Documentation](https://docs.djangoproject.com/en/5.0/topics/settings/)
- [Environment Variables in Python](https://docs.python.org/3/library/os.html#os.environ)
- [Shure System API Documentation](https://developer.shure.com/docs/systems/wireless/api)
- [Django Channels Documentation](https://channels.readthedocs.io/)

## Contributing Configuration Changes

If you need to add new environment variables:

1. Add to `.env.example` with descriptive comments
2. Update this file with documentation
3. Never include real values in `.env.example`
4. Test locally with `.env.local`
5. Document in PR description any new requirements

## Support

For configuration questions:

- Check [Architecture Documentation](./architecture.md)
- Review [Development Guide](./development.md)
- See [Docker Setup Guide](../demo/docker/README.md)
