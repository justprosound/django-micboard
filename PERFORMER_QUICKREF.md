# Performer & Assignment System - Quick Reference

## Core Concepts

| Concept | Model | Purpose |
|---------|-------|---------|
| **User** | Django User + UserProfile | System operators (tech, admin) |
| **Performer** | `Performer` | Device users (talent) |
| **Monitoring Group** | `MonitoringGroup` | RBAC - controls user access |
| **Assignment** | `PerformerAssignment` | Links Performer → WirelessUnit |

## Import Statements

```python
# Models
from micboard.models import Performer, PerformerAssignment, MonitoringGroup

# Services
from micboard.services import PerformerService, PerformerAssignmentService

# User access
from django.contrib.auth.models import User
user = User.objects.get(id=1)
groups = user.get_monitoring_groups()
performers = user.get_accessible_performers()
devices = user.get_accessible_devices()
```

## Performer CRUD

```python
from micboard.services import PerformerService

# CREATE
performer = PerformerService.create_performer(
    name="Jane Smith",
    title="Lead Vocals",
    email="jane@band.com",
    phone="+1234567890",
    photo_file=None,  # Optional file object
    notes="Professional session singer"
)

# READ
performer = PerformerService.get_performer_by_id(performer_id=1)
performer = PerformerService.get_performer_by_name(name="Jane Smith")
all_performers = PerformerService.get_all_performers(active_only=True)
results = PerformerService.search_performers(query="jane", active_only=True)

# UPDATE
performer = PerformerService.update_performer(
    performer=performer,
    title="Co-Lead",  # Only fields to change
    notes="Now co-lead"
)

# DEACTIVATE (soft delete)
PerformerService.deactivate_performer(performer=performer)
PerformerService.reactivate_performer(performer=performer)

# DELETE (hard delete)
PerformerService.delete_performer(performer=performer)

# STATISTICS
count = PerformerService.count_total_performers(active_only=True)
with_assignments = PerformerService.get_performers_with_assignments()
```

## Assignment Management

```python
from micboard.services import PerformerAssignmentService

# CREATE
assignment = PerformerAssignmentService.create_assignment(
    performer=performer,
    wireless_unit=unit,
    monitoring_group=group,
    priority="high",           # low, normal, high, critical
    alert_enabled=True,
    notes="Lead microphone",
    assigned_by=tech_user
)

# READ
performer_assignments = PerformerAssignmentService.get_performer_assignments(
    performer=performer
)
unit_assignments = PerformerAssignmentService.get_unit_assignments(
    wireless_unit=unit
)
group_assignments = PerformerAssignmentService.get_group_assignments(
    monitoring_group=group
)

# Assignments with alerts
alert_assignments = PerformerAssignmentService.get_assignments_needing_alerts(
    monitoring_group=group,
    after=datetime.now() - timedelta(hours=1)
)

# UPDATE
assignment = PerformerAssignmentService.update_assignment(
    assignment=assignment,
    priority="critical",
    alert_enabled=True,
    notes="Changed to critical"
)

# Alert Management
PerformerAssignmentService.update_alert_status(
    assignment=assignment,
    alert_enabled=False
)

# DEACTIVATE/REACTIVATE
PerformerAssignmentService.deactivate_assignment(assignment=assignment)
PerformerAssignmentService.reactivate_assignment(assignment=assignment)

# DELETE
PerformerAssignmentService.delete_assignment(assignment=assignment)

# STATISTICS
total = PerformerAssignmentService.count_total_assignments()
with_alerts = PerformerAssignmentService.count_assignments_with_alerts()
```

## User Access Control (RBAC)

```python
# Get user's monitoring groups
user = User.objects.get(id=1)
groups = user.get_monitoring_groups()  # Returns MonitoringGroup queryset

# Get performers visible to user
accessible_performers = user.get_accessible_performers()
# Internally: Gets all performers assigned via user's MonitoringGroups

# Get devices visible to user
accessible_devices = user.get_accessible_devices()
# Internally: Gets all WirelessUnits assigned via user's MonitoringGroups
```

## Query Optimization

```python
from micboard.models import Performer, PerformerAssignment

# Optimize performer queries
performers = Performer.objects.active().with_assignments()
# Prefetches: assignments, assignments__wireless_unit

# Optimize assignment queries
assignments = (
    PerformerAssignment.objects
    .filter(monitoring_group=group)
    .with_performer_and_unit()
)
# Selects related: performer, wireless_unit, wireless_unit__base_chassis, location

# Get alert-enabled assignments
alert_assignments = PerformerAssignment.objects.needing_alerts(
    after=datetime.now() - timedelta(hours=24)
)
```

## Alert Preferences

```python
assignment = PerformerAssignment.objects.first()

# Get alert prefs as dict
alerts = assignment.get_alert_preferences()
# Returns: {
#     'battery_low': True,
#     'signal_loss': True,
#     'audio_low': False,
#     'device_offline': True
# }

# Update individual alerts
assignment.alert_on_battery_low = False
assignment.alert_on_signal_loss = True
assignment.save()
```

## Common Patterns

### Bulk Create Performers
```python
performers = [
    PerformerService.create_performer(
        name=f"Performer {i}",
        title="Band Member"
    )
    for i in range(10)
]
```

### Assign Performers to Multiple Units
```python
performer = PerformerService.get_performer_by_id(1)
for unit in WirelessUnit.objects.filter(chassis=chassis):
    PerformerAssignmentService.create_assignment(
        performer=performer,
        wireless_unit=unit,
        monitoring_group=group
    )
```

### Monitor Alert-Enabled Assignments
```python
# Get all assignments that should generate alerts
alert_assignments = PerformerAssignmentService.get_assignments_needing_alerts(
    monitoring_group=stage_group
)

for assignment in alert_assignments:
    if assignment.wireless_unit.battery_low:
        notify_user(assignment.assigned_by,
                    f"Low battery: {assignment.performer.name}")
```

### Disable Performer for Event
```python
performer = PerformerService.get_performer_by_id(1)
PerformerService.deactivate_performer(performer=performer)
# All assignments automatically filtered out in queries
```

### Multiple Performers Per Unit (Shared)
```python
# Unique constraint only on (performer, unit) pair
# So same unit can have multiple performers at different times/events

for performer in festival_headliners:
    PerformerAssignmentService.create_assignment(
        performer=performer,
        wireless_unit=shared_stage_mic,
        monitoring_group=festival_group
    )
```

## Migration from DeviceAssignment

```python
# OLD (LEGACY - Still works but deprecated)
from micboard.services import AssignmentService
assignment = AssignmentService.create_assignment(
    user=tech_user,
    channel=rf_channel,
    alert_enabled=True
)

# NEW (Recommended)
from micboard.services import PerformerService, PerformerAssignmentService
performer = PerformerService.create_performer(name="Performer Name")
assignment = PerformerAssignmentService.create_assignment(
    performer=performer,
    wireless_unit=unit,
    monitoring_group=group
)
```

## MultiTenant Support

```python
# All new models support multi-tenancy automatically
# No special configuration needed if settings enabled

# Queries automatically filtered by organization/campus
performers = Performer.objects.all()
# Behind the scenes: Filters by active org/campus context

assignments = PerformerAssignment.objects.all()
# Same automatic filtering applied
```

## Soft Delete Patterns

```python
# Deactivate (soft delete)
PerformerService.deactivate_performer(performer)
# performer.is_active = False
# Performer appears inactive but not deleted

# Query only active
active_performers = Performer.objects.active()
# Uses: .filter(is_active=True)

# Query all (including inactive)
all_performers = Performer.objects.all()  # Note: _all_
```

## Audit Trail

```python
assignment = PerformerAssignment.objects.first()

# Who created this?
creator = assignment.assigned_by  # User who created assignment

# When created?
created_at = assignment.assigned_at  # Timestamp

# When last updated?
updated_at = assignment.updated_at  # Auto-updated on save
```

## Common Queries

```python
from micboard.models import Performer, PerformerAssignment
from django.db.models import Count

# Count performers per group
group_count = (
    Performer.objects
    .annotate(group_count=Count('assignments__monitoring_group', distinct=True))
)

# Get performers with no assignments
unassigned = Performer.objects.exclude(assignments__isnull=False)

# Get assignments by priority
critical = PerformerAssignment.objects.filter(priority='critical')

# Get units with multiple performers
from django.db.models import Count
crowded = (
    PerformerAssignment.objects
    .values('wireless_unit')
    .annotate(count=Count('id'))
    .filter(count__gt=1)
)

# Get recently updated assignments
from datetime import timedelta
recent = (
    PerformerAssignment.objects
    .filter(updated_at__gte=datetime.now()-timedelta(hours=24))
)
```

## Troubleshooting

### "Performer already assigned to unit"
```python
# unique_together enforces one assignment per (performer, unit)
# Solution: Delete old assignment first or reuse existing
try:
    assignment = PerformerAssignmentService.create_assignment(...)
except IntegrityError:
    assignment = PerformerAssignment.objects.get(
        performer=performer, wireless_unit=unit
    )
```

### "MonitoringGroup not found"
```python
# Check user's groups
user = User.objects.get(id=1)
if not user.get_monitoring_groups():
    # User not in any monitoring groups
    # Add via admin interface or programmatically
    group = MonitoringGroup.objects.first()
    group.users.add(user)
```

### Access denied (user can't see performer)
```python
# Check if performer is in user's accessible groups
accessible = user.get_accessible_performers()
if performer_id not in [p.id for p in accessible]:
    # Performer not in user's MonitoringGroups
    # Add assignment in correct group
```

## Performance Considerations

- Use `.with_assignments()` on Performer queries
- Use `.with_performer_and_unit()` on PerformerAssignment queries
- Use `.needing_alerts()` for alert processing
- Indexes exist on: performer, wireless_unit, monitoring_group, priority, is_active
- Soft-delete doesn't reduce query load (add `active()` filter)

## Related Documentation

- **Full Architecture:** `micboard/docs/PERFORMER_ASSIGNMENT_ARCHITECTURE.md`
- **Service Methods:** Docstrings in `micboard/services/performer.py` and `performer_assignment.py`
- **Model Fields:** Docstrings in `micboard/models/monitoring/performer.py` and `performer_assignment.py`
