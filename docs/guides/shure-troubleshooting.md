# Troubleshooting

Common issues and solutions for django-micboard with Shure wireless microphone systems.

## Connection Issues

### Shure API Connection Failed

**Symptoms:**
- "Connection refused" errors
- Authentication failures
- SSL certificate errors

**Solutions:**

1. **Verify API Configuration:**
   ```python
   # Check settings.py
   MICBOARD_SHURE_API = {
       'BASE_URL': 'https://your-shure-system.local',
       'USERNAME': 'admin',
       'PASSWORD': 'correct-password',
       'VERIFY_SSL': False,  # For self-signed certificates
   }
   ```

2. **Test API Access:**
   ```bash
   # Test with curl
   curl -k -u admin:password https://your-shure-system.local/api/v1
   ```

3. **Check Network Connectivity:**
   ```bash
   # Ping the Shure system
   ping your-shure-system.local

   # Test port connectivity
   nc -zv your-shure-system.local 443
   ```

4. **Review Shure System Logs:**
   - Access Shure web interface
   - Check System → Logs
   - Look for API authentication attempts

### Device Discovery Problems

**Symptoms:**
- No devices found during discovery
- Devices appear offline
- Incomplete device information

**Solutions:**

1. **Verify Discovery IPs:**
   ```bash
   # Check configured IPs
   python manage.py shell -c "from micboard.models import DiscoveryIP; print(list(DiscoveryIP.objects.values_list('ip', flat=True)))"
   ```

2. **Add Device IPs Manually:**
   ```bash
   # Add specific IPs
   python manage.py add_shure_devices --ips 192.168.1.100 192.168.1.101
   ```

3. **Check Device Network Configuration:**
   - Ensure devices are on the same network
   - Verify IP addresses are static
   - Check DHCP reservations

4. **Test Individual Device Access:**
   ```python
   from micboard.integrations.shure.client import ShureSystemAPIClient
   client = ShureSystemAPIClient()
   try:
       devices = client.get_devices()
       print(f"Found {len(devices)} devices")
   except Exception as e:
       print(f"Error: {e}")
   ```

## Data Synchronization Issues

### Stale Device Data

**Symptoms:**
- Battery levels not updating
- RF signals show old values
- Device status incorrect

**Solutions:**

1. **Check Polling Status:**
   ```bash
   # Run manual poll
   python manage.py poll_devices --manufacturer shure --verbose
   ```

2. **Verify Polling Process:**
   ```bash
   # Check running processes
   ps aux | grep poll_devices

   # Kill stuck processes
   pkill -f poll_devices
   ```

3. **Review Polling Logs:**
   ```python
   # Check Django logs
   import logging
   logger = logging.getLogger('micboard')
   # Ensure log level is DEBUG
   ```

4. **Test API Response Times:**
   ```python
   import time
   from micboard.integrations.shure.client import ShureSystemAPIClient

   client = ShureSystemAPIClient()
   start = time.time()
   devices = client.get_devices()
   print(f"API call took {time.time() - start:.2f} seconds")
   ```

### WebSocket Connection Problems

**Symptoms:**
- Real-time updates not working
- WebSocket connection errors
- Frontend shows stale data

**Solutions:**

1. **Verify ASGI Configuration:**
   ```python
   # asgi.py should include:
   from micboard.routing import websocket_urlpatterns

   application = ProtocolTypeRouter({
       'http': get_asgi_application(),
       'websocket': URLRouter(websocket_urlpatterns),
   })
   ```

2. **Check Redis Connectivity:**
   ```bash
   # Test Redis
   redis-cli ping

   # Check Redis logs
   tail -f /var/log/redis/redis-server.log
   ```

3. **Test WebSocket Connection:**
   ```javascript
   // Browser console
   const ws = new WebSocket('ws://your-server/ws/devices/');
   ws.onopen = () => console.log('Connected');
   ws.onerror = (e) => console.error('Error:', e);
   ```

4. **Monitor Channel Layer:**
   ```python
   from channels.layers import get_channel_layer
   channel_layer = get_channel_layer()
   print(f"Channel layer: {channel_layer}")
   ```

## Performance Issues

### Slow Page Loads

**Symptoms:**
- Admin interface loads slowly
- API responses delayed
- High server resource usage

**Solutions:**

1. **Optimize Database Queries:**
   ```python
   # Use select_related for foreign keys
   devices = Device.objects.select_related('manufacturer', 'location').all()
   ```

2. **Implement Caching:**
   ```python
   from django.core.cache import cache

   # Cache device data
   devices = cache.get('devices')
   if not devices:
       devices = Device.objects.all()
       cache.set('devices', devices, 300)  # 5 minutes
   ```

3. **Check Database Indexes:**
   ```sql
   -- Ensure indexes on frequently queried fields
   CREATE INDEX CONCURRENTLY idx_device_manufacturer ON micboard_device(manufacturer_id);
   CREATE INDEX CONCURRENTLY idx_device_last_updated ON micboard_device(last_updated);
   ```

4. **Monitor Query Performance:**
   ```python
   from django.db import connection
   from django.conf import settings

   settings.DEBUG = True
   # Run queries and check connection.queries
   ```

### High Memory Usage

**Symptoms:**
- Server memory consumption increasing
- Application crashes with OOM errors
- Slow response times

**Solutions:**

1. **Implement Pagination:**
   ```python
   from django.core.paginator import Paginator

   devices = Device.objects.all()
   paginator = Paginator(devices, 50)  # 50 per page
   page = paginator.page(1)
   ```

2. **Use Iterators for Large Queries:**
   ```python
   # Instead of loading all objects
   for device in Device.objects.iterator():
       process_device(device)
   ```

3. **Configure Connection Pooling:**
   ```python
   # settings.py
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'CONN_MAX_AGE': 60,  # Keep connections alive
           'OPTIONS': {
               'pool': {
                   'minconn': 1,
                   'maxconn': 20,
               }
           }
       }
   }
   ```

4. **Monitor Memory Usage:**
   ```python
   import psutil
   import os

   process = psutil.Process(os.getpid())
   print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.2f} MB")
   ```

## Authentication and Permissions

### API Authentication Errors

**Symptoms:**
- 401 Unauthorized responses
- Authentication failed messages

**Solutions:**

1. **Verify Credentials:**
   ```python
   # Test authentication
   from micboard.integrations.shure.client import ShureSystemAPIClient
   client = ShureSystemAPIClient()
   try:
       client._make_request('GET', '/api/v1')
       print("Authentication successful")
   except Exception as e:
       print(f"Authentication failed: {e}")
   ```

2. **Check Credential Storage:**
   ```python
   # Ensure credentials are properly set
   from django.conf import settings
   api_config = getattr(settings, 'MICBOARD_SHURE_API', {})
   print("API Config:", {k: '***' if 'password' in k.lower() else v for k, v in api_config.items()})
   ```

3. **Review Shure System Authentication:**
   - Check user permissions in Shure interface
   - Verify API user has necessary permissions
   - Reset API password if needed

### Permission Errors

**Symptoms:**
- Access denied to admin functions
- API endpoints return 403 Forbidden

**Solutions:**

1. **Check Django Permissions:**
   ```python
   # Verify user permissions
   user = User.objects.get(username='admin')
   print("Is staff:", user.is_staff)
   print("Is superuser:", user.is_superuser)
   ```

2. **Review Object Permissions:**
   ```python
   from guardian.shortcuts import get_objects_for_user
   devices = get_objects_for_user(user, 'micboard.view_device')
   print(f"User can view {len(devices)} devices")
   ```

3. **Configure Admin Permissions:**
   ```python
   # settings.py
   MICBOARD_ADMIN_PERMISSIONS = {
       'restrict_by_location': True,
       'require_change_approval': False,
   }
   ```

## Device-Specific Issues

### Battery Level Problems

**Symptoms:**
- Battery levels not updating
- Incorrect battery percentages
- Charging status wrong

**Solutions:**

1. **Check Device Firmware:**
   - Ensure devices run compatible firmware
   - Update firmware if necessary
   - Check Shure release notes

2. **Verify Battery Reporting:**
   ```python
   # Test battery API
   from micboard.integrations.shure.client import ShureSystemAPIClient
   client = ShureSystemAPIClient()
   device = client.get_device('device_id')
   print(f"Battery: {device.get('battery_level')}")
   ```

3. **Calibrate Battery Sensors:**
   - Some Shure devices require battery calibration
   - Follow device-specific calibration procedures

### RF Signal Issues

**Symptoms:**
- RF signal strength incorrect
- Interference not detected
- Channel changes not reflected

**Solutions:**

1. **Check Antenna Configuration:**
   - Verify antenna connections
   - Check antenna placement
   - Test antenna signal strength

2. **Review Frequency Settings:**
   ```python
   # Check device frequency
   device = Device.objects.get(device_id='SHURE001')
   print(f"Frequency: {device.frequency}")
   ```

3. **Monitor Interference:**
   - Use spectrum analyzer tools
   - Check for local interference sources
   - Adjust channel assignments

## Logging and Debugging

### Enable Debug Logging

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'micboard.log',
        },
    },
    'loggers': {
        'micboard': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'micboard.integrations.shure': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
```

### Debug Commands

```bash
# Test API connectivity
python manage.py shell -c "
from micboard.integrations.shure.client import ShureSystemAPIClient
client = ShureSystemAPIClient()
print('Testing API...')
try:
    health = client.check_health()
    print('Health:', health)
except Exception as e:
    print('Error:', e)
"

# Check database status
python manage.py shell -c "
from micboard.models import Device
print(f'Total devices: {Device.objects.count()}')
print(f'Online devices: {Device.objects.filter(is_online=True).count()}')
"

# Test WebSocket
python manage.py shell -c "
from channels.layers import get_channel_layer
layer = get_channel_layer()
print('Channel layer:', layer)
"
```

## Common Error Messages

### "Connection timeout"

**Cause:** Network issues or slow API responses
**Solution:** Increase timeout values, check network connectivity

### "SSL certificate verify failed"

**Cause:** Invalid or self-signed SSL certificate
**Solution:** Set `VERIFY_SSL = False` for development, or install proper certificate

### "Device not found"

**Cause:** Device not in discovery range or offline
**Solution:** Add device IP manually, check device power and network

### "Authentication failed"

**Cause:** Incorrect API credentials
**Solution:** Verify username/password in Shure system and Django settings

### "WebSocket connection failed"

**Cause:** ASGI/Rails configuration or Redis issues
**Solution:** Check ASGI setup, verify Redis connectivity, review firewall settings

## Getting Help

### Diagnostic Information

When reporting issues, include:

```bash
# System information
python -c "import django; print(f'Django: {django.VERSION}')"

# Package versions
pip list | grep -E "(django|channels|micboard)"

# Configuration check
python manage.py shell -c "
from django.conf import settings
print('Shure API configured:', hasattr(settings, 'MICBOARD_SHURE_API'))
print('Channels configured:', hasattr(settings, 'CHANNEL_LAYERS'))
"
```

### Support Resources

- [GitHub Issues](https://github.com/justprosound/django-micboard/issues)
- [Shure API Documentation](https://shure.secure.force.com/apiexplorer)
- [Django Channels Documentation](https://channels.readthedocs.io/)
- [Django Micboard Documentation](https://django-micboard.readthedocs.io/)
