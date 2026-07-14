# Admin Interface

The django-micboard admin interface provides comprehensive management and monitoring of your Shure wireless microphone system.

## Accessing the Admin

Navigate to `/admin/` in your Django application after logging in with admin credentials.

## Device Management

### Device List

The main device list (`/admin/micboard/device/`) shows all discovered devices:

- **Device Information**: Name, model, manufacturer, device ID
- **Status Indicators**:
  - 🔋 Battery level (color-coded: green > 50%, yellow 20-50%, red < 20%)
  - 📶 RF signal strength
  - 🌐 Online/offline status
  - 📍 Location and user assignment
- **Timestamps**: Last update, created date
- **Actions**: Edit, delete, assign user/location

### Adding Devices

**Automatic Discovery:**
```bash
uv run python manage.py sync_discovery --manufacturer shure --scan-cidrs
```

Configure CIDR ranges in the admin discovery settings before running the sync.

**Manual Addition:**
1. Click "Add Device" in admin
2. Select Manufacturer: Shure
3. Enter Device ID and IP address
4. Optionally assign location and user

### Device Details

Click on any device to view detailed information:

- **Real-time Metrics**: Live battery, RF, audio levels
- **Device Configuration**: Model, firmware, serial number
- **Network Information**: IP address, MAC address
- **Assignment History**: Previous users/locations
- **Status Log**: Recent status changes

## User Assignments

### Managing Assignments

Navigate to `/admin/micboard/assignment/` to manage device assignments:

- **Create Assignment**: Assign device to user with alert preferences
- **Bulk Assignment**: Assign multiple devices at once
- **Assignment History**: Track assignment changes over time

### Assignment Features

```python
from micboard.services.core.performer_assignment import PerformerAssignmentService

# Create a performer-to-wireless-unit assignment
assignment = PerformerAssignmentService.create_assignment(
    performer_id=performer.id,
    unit_id=wireless_unit.id,
    group_id=monitoring_group.id,
    user=user,
    alert_on_battery_low=True,
)
```

## Location Management

### Location Setup

Create and manage locations at `/admin/micboard/location/`:

- **Location Hierarchy**: Building → Room → Zone
- **Device Assignment**: Assign devices to locations
- **Capacity Tracking**: Monitor device density per location

### Location Analytics

View location-based analytics:

- Device count per location
- Battery health by area
- Signal strength mapping
- Usage patterns

## Connection Monitoring

### Real-time Connection Status

Monitor WebSocket and API connections at `/admin/micboard/realtimeconnection/`:

- **Connection State**: Connected, disconnected, error
- **Health Metrics**: Latency, error rate, uptime
- **Automatic Recovery**: Failed connection retry logic

### Connection Health Checks

```bash
# Check all connections
uv run python manage.py realtime_status

# Show detailed connection records
uv run python manage.py realtime_status --verbose
```

## Manufacturer Management

### Manufacturer Configuration

Configure manufacturer settings at `/admin/micboard/manufacturer/`:

- **Shure Settings**: API endpoints, credentials, timeouts
- **Plugin Configuration**: Enable/disable manufacturers
- **API Rate Limits**: Configure request limits

## Discovery Management

### Discovery IP Ranges

Manage device discovery at `/admin/micboard/discovery/`:

- **IP Range Configuration**: Add CIDR ranges for scanning
- **Discovery Scheduling**: Automated discovery intervals
- **Manual Discovery**: On-demand device scanning

## System Health Dashboard

### Overview Dashboard

The main admin index provides system health overview:

- **Device Summary**: Total devices, online/offline counts
- **Battery Status**: Devices by battery level ranges
- **Alert Summary**: Active alerts and notifications
- **Connection Status**: API and WebSocket health

### Health Metrics

Monitor system performance:

- Polling success rates
- API response times
- WebSocket connection counts
- Error rates and trends

## Custom Admin Features

### Custom Actions

Bulk operations available in admin lists:

- **Bulk Status Update**: Mark multiple devices online/offline
- **Bulk Assignment**: Assign multiple devices to user/location
- **Bulk Delete**: Remove multiple devices
- **Export Data**: CSV export of device information

### Custom Admin Extensions

To extend the admin interface with custom fields:

```python
# custom_admin.py
from django.contrib import admin
from micboard.admin.receivers import WirelessChassisAdmin
from micboard.models.hardware.wireless_chassis import WirelessChassis

admin.site.unregister(WirelessChassis)


@admin.register(WirelessChassis)
class CustomWirelessChassisAdmin(WirelessChassisAdmin):
    list_display = ("name", "api_device_id", "ip", "status")
    search_fields = ("name", "api_device_id", "serial_number")
    list_filter = ("manufacturer", "status", "location")
```

## Security and Permissions

### Admin Permissions

Configure admin access controls:

- **User Permissions**: Read-only vs. full access
- **Object Permissions**: Location-based access control
- **Audit Logging**: Track all admin actions

### API Access Control

Secure API endpoints:

```python
# settings.py
MICBOARD_API_PERMISSIONS = {
    'require_authentication': True,
    'allow_cors_origins': ['https://your-domain.com'],
}
```

## Troubleshooting

### Common Admin Issues

**Devices not appearing:**
- Check discovery IP ranges
- Verify API credentials
- Review Django logs for errors

**Real-time updates not working:**
- Confirm WebSocket configuration
- Check Redis connectivity
- Verify ASGI setup

**Permission errors:**
- Review user group permissions
- Check object-level permissions
- Verify authentication settings

### Performance Optimization

**Large device counts:**
- Implement pagination in admin lists
- Use select_related for foreign keys
- Configure database indexes

**Slow page loads:**
- Enable admin caching
- Optimize queryset filtering
- Use admin list_select_related

## Advanced Features

### Service Integration

Use the public service layer in host-project views and admin extensions:

```python
from micboard.services.core.hardware_query import HardwareQueryService

active_chassis = HardwareQueryService.get_active_chassis()
```

### Export and Reporting

Generate reports from admin data:

- **CSV Export**: Device inventories
- **PDF Reports**: System health summaries
- **Scheduled Reports**: Automated report generation
