# Monitoring Devices

Learn how to monitor your Shure wireless microphone system with django-micboard.

## Device Status Overview

Django Micboard provides real-time monitoring of:

- **Battery Levels** - Current charge percentage and status
- **RF Signal Strength** - Signal quality and interference indicators
- **Audio Levels** - Input/output levels and peak indicators
- **Device Status** - Online/offline state and connection health
- **Location Tracking** - Device location and assignment status

## Admin Interface

Access the monitoring interface at `/admin/` in your Django application.

### Device List View

The main device list shows all discovered devices with key metrics:

- Device name and model
- Current battery level (with color coding)
- RF signal strength
- Online status
- Last update time
- Assigned user/location

### Real-time Updates

Device status updates automatically via WebSocket connections:

- Battery levels refresh every 30 seconds
- RF signals update continuously
- Status changes appear immediately
- Connection health is monitored

## Management Commands

### Continuous Polling

For production monitoring, run continuous device polling:

```bash
# Poll Shure devices continuously
python manage.py poll_devices --manufacturer shure --continuous

# Poll with custom interval (default 30 seconds)
python manage.py poll_devices --manufacturer shure --continuous --interval 60
```

### Health Monitoring

Monitor connection health and detect issues:

```bash
# Check all connections
python manage.py check_connections

# Check specific manufacturer
python manage.py check_connections --manufacturer shure
```

## Alerts and Notifications

### Battery Alerts

Configure alerts for low battery conditions:

- Set threshold levels (default: 20%)
- Enable/disable per device or globally
- Email notifications (planned)
- Admin interface warnings

### RF Signal Alerts

Monitor signal quality:

- Low signal strength warnings
- Interference detection
- Channel conflicts
- Automatic channel scanning

## Device Assignment

### User Assignments

Assign devices to specific users:

```python
from micboard.services import AssignmentService

# Assign device to user
assignment = AssignmentService.create_assignment(
    user=user,
    device=device,
    alert_enabled=True
)
```

### Location Tracking

Track devices by location:

```python
from micboard.services import LocationService

# Create location
location = LocationService.create_location(
    name="Main Stage",
    description="Primary performance area"
)

# Assign device to location
LocationService.assign_device_to_location(device, location)
```

## Troubleshooting

### Device Not Updating

**Check connection status:**
```bash
python manage.py check_connections --manufacturer shure
```

**Verify API access:**
```bash
python manage.py poll_devices --manufacturer shure --dry-run
```

**Check device logs:**
- Review Django admin logs
- Check Shure System API logs
- Verify network connectivity

### WebSocket Issues

**Test WebSocket connection:**
- Open browser developer tools
- Check Network tab for WebSocket connections
- Verify ASGI configuration

**Redis connection:**
```bash
# Test Redis connectivity
python manage.py shell -c "from channels.layers import get_channel_layer; print(get_channel_layer())"
```

### Performance Issues

**Monitor polling performance:**
```bash
# Check polling duration
python manage.py poll_devices --manufacturer shure --verbose
```

**Database optimization:**
- Ensure proper indexing on device models
- Monitor query performance
- Check connection pooling

## Advanced Monitoring

### Custom Dashboards

Create custom monitoring views:

- Filter by location or user
- Sort by battery level or signal strength
- Export device reports
- Historical trend analysis

### API Integration

Use the REST API for custom monitoring:

```python
# Get device status
GET /api/v1/devices/

# Get battery levels
GET /api/v1/devices/?battery_level__lt=20

# Real-time updates via WebSocket
ws://your-server/ws/devices/
```

### Health Checks

Implement health check endpoints:

```python
from micboard.services import ConnectionHealthService

# Check overall system health
health = ConnectionHealthService.get_overall_health_status()
print(f"Online devices: {health['online_receivers']}/{health['total_receivers']}")
```
