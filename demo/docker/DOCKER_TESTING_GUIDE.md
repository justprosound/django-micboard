# Docker Setup for Live Device Testing

**Last Updated:** January 22, 2026

## Overview

This guide explains how to set up and use the Docker environment for testing django-micboard with live Shure devices, including devices at Georgia Tech.

## Quick Start

### 1. Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker Compose v2+
- Access to Shure System API (local or via VPN)
- Shure API shared key

### 2. Initial Setup

```bash
# Navigate to docker directory
cd demo/docker

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env  # or your preferred editor
```

### 3. Start the Container

```bash
# Build and start
docker compose up --build

# Or run in detached mode
docker compose up -d --build

# View logs
docker compose logs -f

# Stop
docker compose down
```

## Configuration

### Local Testing (Windows)

Configure `.env` for local Shure System API:

```bash
MICBOARD_SHURE_API_BASE_URL=http://host.docker.internal:10000
MICBOARD_SHURE_API_SHARED_KEY=your-key-from-sharedkey.txt
MICBOARD_SHURE_API_VERIFY_SSL=true
```

**Finding the shared key on Windows:**
```
C:\ProgramData\Shure\SystemAPI\Standalone\Security\sharedkey.txt
```

### Georgia Tech VPN Testing

Configure `.env` for GT device access:

```bash
# Use actual device IP on GT network
MICBOARD_SHURE_API_BASE_URL=http://172.21.x.x:10000

# Your Shure API shared key
MICBOARD_SHURE_API_SHARED_KEY=your-shared-key

# Device IPs to discover (comma-separated)
MICBOARD_DISCOVERY_IPS=172.21.1.100,172.21.1.101,172.21.1.102

# Network timeout for VPN connections
MICBOARD_NETWORK_TIMEOUT=30

# Optional: Network GUID for discovery
MICBOARD_SHURE_NETWORK_GUID={A283C67D-499A-4B7E-B628-F74E8061FCE2}
```

**VPN Connection:**
1. Connect to Georgia Tech VPN
2. Note device IPs from network discovery
3. Update `MICBOARD_SHURE_API_BASE_URL` with primary device IP
4. List all device IPs in `MICBOARD_DISCOVERY_IPS`

## Docker Compose Profiles

### Default Profile

Basic setup with django-micboard only:

```bash
docker compose up
```

### With Redis

Include Redis for caching and Django-Q:

```bash
docker compose --profile with-redis up
```

## Network Modes

### Bridge Mode (Default)

Suitable for local development and most VPN scenarios:

```yaml
# Already configured in docker-compose.yml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### Host Mode (Advanced)

For direct network access (uncomment in docker-compose.yml):

```yaml
network_mode: "host"
```

**When to use host mode:**
- Direct connection to GT network devices
- Complex networking requirements
- Troubleshooting connectivity issues

## Testing Workflow

### 1. Verify API Connection

```bash
# Exec into container
docker compose exec micboard-demo bash

# Test API health
curl http://localhost:8000/api/health/

# Test Shure API connection
python manage.py shell
>>> from micboard.integrations.shure.client import ShureSystemAPIClient
>>> client = ShureSystemAPIClient()
>>> client.check_health()
```

### 2. Run Device Discovery

```bash
# Inside container
python manage.py poll_devices --manufacturer shure

# Or use discovery script
python scripts/shure_api_health_check.py
```

### 3. Check Device Population

```bash
# Django admin
# Navigate to: http://localhost:8000/admin/

# Or via API
curl http://localhost:8000/api/v1/receivers/
```

### 4. Monitor Logs

```bash
# Follow logs
docker compose logs -f micboard-demo

# Check specific service
docker compose logs redis

# Last 100 lines
docker compose logs --tail=100 micboard-demo
```

## Development Mode

### Hot Reload

The container mounts your local code for development:

```yaml
volumes:
  - ../..:/app:cached
```

**Changes automatically reload** - no rebuild needed for Python code changes.

### Running Commands

```bash
# Django management commands
docker compose exec micboard-demo python manage.py [command]

# Examples:
docker compose exec micboard-demo python manage.py migrate
docker compose exec micboard-demo python manage.py createsuperuser
docker compose exec micboard-demo python manage.py shell

# Run tests
docker compose exec micboard-demo pytest micboard/tests/ -v
```

## Troubleshooting

### Cannot Connect to Shure API

**Symptom:** Connection refused or timeout

**Solutions:**
1. Verify `MICBOARD_SHURE_API_BASE_URL` is correct
2. Check Shure System API is running
3. On Windows, ensure Docker Desktop is using WSL2 backend
4. Test connection from host:
   ```bash
   curl http://localhost:10000/api/v1.0/devices
   ```

### Authentication Failed

**Symptom:** 401 Unauthorized

**Solutions:**
1. Verify `MICBOARD_SHURE_API_SHARED_KEY` matches sharedkey.txt
2. Check key has no extra whitespace
3. Regenerate key if necessary (restart Shure System API)

### GT VPN Connection Issues

**Symptom:** Devices not accessible via VPN

**Solutions:**
1. Verify VPN connection is active
2. Test device connectivity from host:
   ```bash
   ping 172.21.x.x
   curl http://172.21.x.x:10000/api/v1.0/devices
   ```
3. Try `network_mode: "host"` if bridge mode fails
4. Check firewall rules allow Docker traffic
5. Verify GUID matches GT network: `{A283C67D-499A-4B7E-B628-F74E8061FCE2}`

### Container Won't Start

**Symptom:** Exit code 1 or health check failing

**Solutions:**
1. Check logs: `docker compose logs micboard-demo`
2. Verify `.env` file exists and is configured
3. Check migrations:
   ```bash
   docker compose run --rm micboard-demo python manage.py migrate
   ```
4. Rebuild:
   ```bash
   docker compose down
   docker compose build --no-cache
   docker compose up
   ```

### Hot Reload Not Working

**Symptom:** Code changes not reflected

**Solutions:**
1. Restart container: `docker compose restart micboard-demo`
2. Check volume mount is correct in docker-compose.yml
3. Verify file permissions (especially on Linux)
4. Check Docker Desktop file sharing settings

## Performance Optimization

### Build Performance

```bash
# Use BuildKit for faster builds
DOCKER_BUILDKIT=1 docker compose build

# Build specific service
docker compose build micboard-demo
```

### Resource Limits

Add to `docker-compose.yml` if needed:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      memory: 512M
```

## Security Considerations

### Do NOT Commit

- `.env` file with real credentials
- `sharedkey.txt`
- Any files with actual device IPs or network topology

### Production Deployment

For production (not covered here):
- Use secrets management (Docker Swarm secrets, Kubernetes secrets)
- Set `DJANGO_DEBUG=False`
- Configure proper `ALLOWED_HOSTS`
- Use PostgreSQL instead of SQLite
- Set up proper SSL/TLS
- Configure rate limiting
- Enable CSRF protection

## Reference

### Environment Variables

See `demo/docker/.env.example` for complete list.

**Required:**
- `MICBOARD_SHURE_API_BASE_URL`
- `MICBOARD_SHURE_API_SHARED_KEY`

**Optional:**
- `MICBOARD_DISCOVERY_IPS` - Device IPs for discovery
- `MICBOARD_NETWORK_TIMEOUT` - Connection timeout (default: 30s)
- `MICBOARD_POLLING_INTERVAL` - Polling frequency (default: 60s)

### Ports

- `8000` - Django web server
- `6379` - Redis (if using with-redis profile)

### Volumes

- `../..:/app:cached` - Code mount for hot reload
- `redis-data` - Redis persistence (if using Redis)

## Next Steps

1. **Test with mock data** - Use demo fixtures
2. **Connect to local Shure API** - Windows development
3. **Test with GT devices** - VPN connection
4. **Run integration tests** - Full workflow validation
5. **Monitor performance** - Check polling efficiency

## Support

For issues or questions:
- See [PHASE_2_COMPLETION.md](../../PHASE_2_COMPLETION.md) for Shure troubleshooting
- See [docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md](../../docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md) for GUID issues
- Check [scripts/README_SHURE_SCRIPTS.md](../../scripts/README_SHURE_SCRIPTS.md) for diagnostic scripts

---

**Status:** Ready for testing  
**Tested On:** Windows Docker Desktop, Linux Docker Engine
