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

### Device Polling

Run a one-shot poll directly or enqueue it through native Huey:

```bash
# Poll Shure devices now
uv run python manage.py poll_devices --manufacturer shure

# Enqueue one poll through native Huey
uv run python manage.py poll_devices --manufacturer shure --async
```

Use your deployment scheduler to enqueue the one-shot command at the required interval.

### Health Monitoring

Monitor connection health and detect issues:

```bash
# Check all connections
uv run python manage.py realtime_status

# Check specific manufacturer
uv run python manage.py realtime_status --manufacturer shure
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
from micboard.services.core.performer_assignment import PerformerAssignmentService

# Assign a wireless unit to a performer
assignment = PerformerAssignmentService.create_assignment(
    performer_id=performer.id,
    unit_id=wireless_unit.id,
    group_id=monitoring_group.id,
    user=user,
    alert_on_battery_low=True,
)
```

### Location Tracking

Track devices by location:

```python
from micboard.services.core.location import LocationService
from micboard.models.locations.structure import Building

# Create location
building = Building.objects.get(name="Venue")
location = LocationService.create_location(
    building=building,
    name="Main Stage",
    description="Primary performance area",
)

# Assign device to location
LocationService.assign_device_to_location(device=device, location=location)
```

## Troubleshooting

### Device Not Updating

**Check connection status:**
```bash
uv run python manage.py realtime_status --manufacturer shure
```

**Verify API access:**
```bash
uv run python manage.py diagnostic_api_health_check
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
uv run python manage.py shell -c "from channels.layers import get_channel_layer; print(get_channel_layer())"
```

### Performance Issues

**Monitor polling performance:**
```bash
# Run one poll and inspect its completion summary
uv run python manage.py poll_devices --manufacturer shure
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
ws://your-server/ws
```

### Health Checks

Implement health check endpoints:

```python
from micboard.services.monitoring.connection import ConnectionHealthService

# Query connected hardware integrations
active_connections = ConnectionHealthService.get_active_connections()
print(f"Active real-time connections: {active_connections.count()}")
```
