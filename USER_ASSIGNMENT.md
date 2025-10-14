# User Assignment & Monitoring System

## Overview

The micboard app now includes a comprehensive user assignment and monitoring system that allows you to:

- **Assign specific devices/channels to users** for monitoring
- **Organize users into monitoring groups** based on location or team
- **Link devices to physical locations** (buildings/rooms)
- **Configure per-user and per-device alert preferences**
- **Track alert history** for auditing and analysis

## Core Models

### 1. Location

Represents a physical location (building/room) where devices are installed.

**Two integration options:**

**Option A: Link to your existing location model** (e.g., Building, Room):
```python
# Uses GenericForeignKey to link to any model
location = Location.objects.create(
    name="Main Theater",
    content_type=ContentType.objects.get_for_model(YourBuildingModel),
    object_id=your_building.id
)
```

**Option B: Use built-in location fields**:
```python
location = Location.objects.create(
    name="Main Theater",
    building="Arts Center",
    room="Theater 1",
    floor="2nd Floor"
)
```

**Recommendation:** If you have an existing location model in your Django project, modify the `Location` model to add a direct ForeignKey instead of using GenericForeignKey:

```python
# In models.py, replace the GenericForeignKey section with:
class Location(models.Model):
    # Direct foreign key to your location model
    external_location = models.ForeignKey(
        'your_app.YourLocationModel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='micboard_locations'
    )
    # ... rest of the fields
```

### 2. MonitoringGroup

Groups of users who monitor specific devices together (e.g., "Theater Tech Team", "Conference Room A Staff").

```python
group = MonitoringGroup.objects.create(
    name="Theater Tech Team",
    description="Technical staff for the main theater",
    location=theater_location,
    is_active=True
)
group.users.add(user1, user2, user3)
group.devices.add(device1, device2, device3)
```

### 3. DeviceAssignment

Individual device assignments to specific users with customizable alert preferences.

```python
assignment = DeviceAssignment.objects.create(
    user=tech_user,
    device=lead_vocal_mic,
    location=theater_location,
    monitoring_group=tech_team,
    priority='high',  # low, normal, high, critical
    notes='Lead vocalist wireless mic',
    alert_on_battery_low=True,
    alert_on_signal_loss=True,
    alert_on_audio_low=False,
    alert_on_device_offline=True,
    assigned_by=admin_user
)
```

**Unique constraint:** One assignment per user per device (prevents duplicates).

### 4. UserAlertPreference

Global alert preferences for each user (device-specific settings override these).

```python
prefs = UserAlertPreference.objects.create(
    user=tech_user,
    notification_method='both',  # email, websocket, or both
    email_address='alerts@example.com',  # Optional override
    battery_low_threshold=20,  # Alert when battery < 20%
    battery_critical_threshold=10,  # Critical alert < 10%
    quiet_hours_enabled=True,
    quiet_hours_start=time(22, 0),  # 10 PM
    quiet_hours_end=time(8, 0),  # 8 AM
    min_alert_interval=5,  # Minutes between alerts for same device
)
```

### 5. Alert

Tracks all alerts for auditing and analysis.

```python
alert = Alert.objects.create(
    device=mic_device,
    user=tech_user,
    assignment=device_assignment,
    alert_type='battery_low',  # battery_low, battery_critical, signal_loss, etc.
    status='pending',  # pending, sent, acknowledged, resolved, failed
    message='Battery level is 15%',
    device_data={'battery': 15, 'rf_level': 85, ...}  # Snapshot of device state
)
```

## Usage Examples

### Scenario 1: Assign Devices by Building/Room

```python
# Create locations
main_theater = Location.objects.create(
    name="Main Theater",
    building="Arts Center",
    room="Theater 1"
)

conference_room = Location.objects.create(
    name="Conference Room A",
    building="Admin Building",
    room="Room A-101"
)

# Assign devices to locations (would need to add location FK to Device)
# See migration note below

# Assign users to monitor specific locations
DeviceAssignment.objects.create(
    user=theater_tech,
    device=theater_mic_1,
    location=main_theater,
    priority='high'
)
```

### Scenario 2: Team-Based Monitoring

```python
# Create monitoring group
tech_team = MonitoringGroup.objects.create(
    name="Theater Tech Team",
    location=main_theater
)
tech_team.users.add(tech_lead, tech_assistant)

# Add all theater devices to the group
theater_devices = Device.objects.filter(name__icontains='Theater')
tech_team.devices.add(*theater_devices)

# Individual assignments can reference the group
for device in theater_devices:
    DeviceAssignment.objects.create(
        user=tech_lead,
        device=device,
        monitoring_group=tech_team,
        priority='normal'
    )
```

### Scenario 3: Query Assigned Devices

```python
# Get all devices assigned to a user
user_devices = Device.objects.filter(
    assignments__user=request.user,
    assignments__is_active=True
)

# Get all users monitoring a device
device_users = User.objects.filter(
    device_assignments__device=device,
    device_assignments__is_active=True
)

# Get devices in a specific location
location_devices = Device.objects.filter(
    assignments__location=location
).distinct()

# Using the model methods:
device.get_assigned_users()  # Returns QuerySet of users
device.get_monitoring_groups()  # Returns QuerySet of monitoring groups
```

### Scenario 4: Alert Management

```python
# Get pending alerts for a user
pending_alerts = Alert.objects.filter(
    user=request.user,
    status='pending'
).select_related('device', 'assignment')

# Get alert history for a device
device_alerts = Alert.objects.filter(
    device=device,
    created_at__gte=timezone.now() - timedelta(days=7)
).order_by('-created_at')

# Acknowledge an alert
alert.status = 'acknowledged'
alert.acknowledged_at = timezone.now()
alert.save()
```

## Integration with Existing Location Model

If you have an existing location model (e.g., `buildings.models.Building` or `locations.models.Room`), you have two options:

### Option 1: Modify Location Model (Recommended)

Replace the GenericForeignKey in `Location` model with a direct ForeignKey:

```python
class Location(models.Model):
    # Replace the generic foreign key section with:
    building_room = models.ForeignKey(
        'your_app.YourLocationModel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='micboard_locations',
        help_text='Link to your existing location model'
    )

    # Keep the simple fields as fallback
    building = models.CharField(max_length=100, blank=True)
    room = models.CharField(max_length=100, blank=True)
    # ... rest of fields
```

### Option 2: Add ForeignKey to Device Model

Add a direct foreign key from Device to your location model:

```python
# In Device model, add:
location = models.ForeignKey(
    'your_app.YourLocationModel',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='micboard_devices'
)
```

Then create and apply migrations:
```bash
python manage.py makemigrations micboard
python manage.py migrate micboard
```

## API Endpoints for User Assignment

You'll likely want to add these views and API endpoints:

```python
# views.py

@login_required
def my_devices(request):
    """Show devices assigned to the current user"""
    assignments = DeviceAssignment.objects.filter(
        user=request.user,
        is_active=True
    ).select_related('device', 'location', 'monitoring_group')

    return render(request, 'micboard/my_devices.html', {
        'assignments': assignments
    })

@login_required
def my_alerts(request):
    """Show alerts for the current user"""
    alerts = Alert.objects.filter(
        user=request.user
    ).select_related('device', 'assignment').order_by('-created_at')[:50]

    return render(request, 'micboard/my_alerts.html', {
        'alerts': alerts
    })

@require_POST
@login_required
def acknowledge_alert(request, alert_id):
    """Acknowledge an alert"""
    alert = get_object_or_404(Alert, id=alert_id, user=request.user)
    alert.status = 'acknowledged'
    alert.acknowledged_at = timezone.now()
    alert.save()
    return JsonResponse({'success': True})

@login_required
def device_assignments_json(request):
    """API endpoint for user's device assignments (for WebSocket filtering)"""
    assignments = DeviceAssignment.objects.filter(
        user=request.user,
        is_active=True
    ).values('device__slot', 'device__name', 'priority', 'location__name')

    return JsonResponse({
        'assignments': list(assignments),
        'alert_preferences': {
            'battery_low': request.user.alert_preferences.battery_low_threshold if hasattr(request.user, 'alert_preferences') else 20
        }
    })
```

## WebSocket Integration

Update your WebSocket consumer to filter device updates based on user assignments:

```python
# consumers.py

class MicboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

        # Get user's assigned device slots
        if self.scope['user'].is_authenticated:
            # Subscribe only to assigned devices
            user_slots = await self.get_user_device_slots(self.scope['user'])
            for slot in user_slots:
                await self.channel_layer.group_add(
                    f"device_{slot}",
                    self.channel_name
                )
        else:
            # Subscribe to all devices for anonymous/admin
            await self.channel_layer.group_add(
                "micboard_updates",
                self.channel_name
            )

    @database_sync_to_async
    def get_user_device_slots(self, user):
        from .models import DeviceAssignment
        return list(
            DeviceAssignment.objects.filter(
                user=user,
                is_active=True
            ).values_list('device__slot', flat=True)
        )
```

## Admin Interface

All models are registered in the Django admin with:
- **Filtering** by location, priority, status, etc.
- **Search** by user, device, notes
- **Inline editing** for related objects
- **Custom displays** showing counts and relationships
- **Read-only fields** for timestamps and system fields

Access at: `/admin/micboard/`

## Migration Steps

1. **Review the models** in `models.py` and adjust the `Location` model for your needs
2. **Generate and run migrations**:
   ```bash
   python manage.py makemigrations micboard
   python manage.py migrate micboard
   ```

3. **Create locations** in Django admin or via script
4. **Create monitoring groups** for your teams
5. **Assign devices to users**
6. **Configure alert preferences** for each user

## Next Steps

- **Implement alert generation logic** in `poll_devices.py` management command
- **Add email notification** functionality
- **Create user-facing views** for assignments and alerts
- **Update WebSocket consumer** to filter by user assignments
- **Add API endpoints** for mobile apps or external systems

## Notes

- The `Alert` model prevents manual creation in admin (alerts should be generated programmatically)
- Unique constraint on `DeviceAssignment` prevents duplicate user-device pairs
- All models include timestamps for auditing
- Alert preferences on `DeviceAssignment` override user's global preferences
- Quiet hours prevent alerts during specified time windows
