# User-Performer-Device Assignment & Alert Management Architecture

## Overview

This document describes the refactored user-performer-device assignment and alert management system in django-micboard. The new architecture separates concerns between:

1. **Users** (Technicians and Admins) - Monitor and control operations
2. **Performers** (Device Users/Talent) - Assigned to Wireless Units with metadata
3. **Monitoring Groups** - RBAC mechanism controlling user access to devices

## Core Concepts

### Users (Technicians & Admins)

**Model:** `UserProfile` (Django User + profile)

Users are system operators who:
- Manage performer assignments
- Monitor device status via MonitoringGroups
- Control alerts and notifications
- Belong to one or more `MonitoringGroup` instances

**Key Methods:**
```python
user.get_monitoring_groups()        # Groups user belongs to
user.get_accessible_performers()    # Performers visible to user
user.get_accessible_devices()       # Devices visible to user
```

### Performers (Talent/Device Users)

**Model:** `Performer` (new)

Performers are device users with:
- Name, title, role description
- Photo/avatar
- Contact info (email, phone)
- Assignments to one or more WirelessUnits
- Status (active/inactive)

**Key Methods:**
```python
performer.get_assigned_units()      # Wireless units assigned
performer.get_monitoring_groups()   # Groups managing assignments
```

### Performer Assignments

**Model:** `PerformerAssignment` (new)

Links a Performer to a WirelessUnit with:
- Alert preferences (battery, signal loss, audio, offline)
- Priority level (low, normal, high, critical)
- Notes and metadata
- Assignment audit trail (assigned_by, assigned_at, updated_at)
- Unique constraint: One assignment per (performer, wireless_unit) pair

**Service:** `PerformerAssignmentService`

```python
from micboard.services import PerformerAssignmentService

# Create assignment
assignment = PerformerAssignmentService.create_assignment(
    performer=performer_obj,
    wireless_unit=unit_obj,
    monitoring_group=group_obj,
    priority="high",
    alert_enabled=True,
    notes="Lead vocalist"
)

# Get assignments
assignments = PerformerAssignmentService.get_performer_assignments(performer=performer)
group_assignments = PerformerAssignmentService.get_group_assignments(monitoring_group=group)

# Update alerts
PerformerAssignmentService.update_alert_status(assignment=assignment, alert_enabled=True)

# Deactivate/reactivate
PerformerAssignmentService.deactivate_assignment(assignment=assignment)
PerformerAssignmentService.reactivate_assignment(assignment=assignment)
```

### Performer Management

**Service:** `PerformerService`

```python
from micboard.services import PerformerService

# Create performer
performer = PerformerService.create_performer(
    name="Jane Smith",
    title="Lead Vocalist",
    email="jane@example.com",
    photo_file=image_file
)

# Update performer
performer = PerformerService.update_performer(
    performer=performer,
    title="Co-Lead Vocalist",
    notes="Updated role"
)

# Search & retrieve
performers = PerformerService.search_performers(query="jane")
performer = PerformerService.get_performer_by_id(performer_id=123)

# Soft delete
PerformerService.deactivate_performer(performer=performer)
PerformerService.reactivate_performer(performer=performer)

# Statistics
count = PerformerService.count_total_performers(active_only=True)
with_assignments = PerformerService.get_performers_with_assignments()
```

### Monitoring Groups (RBAC)

**Model:** `MonitoringGroup` (existing, enhanced)

Groups define:
- Which users (technicians/admins) can manage assignments
- Which performers and devices are visible to those users
- Organizational boundaries and responsibilities

**Relationship:**
```
User --belongsto--> MonitoringGroup <--manages--> PerformerAssignment
                                                      |
                                                      v
                                                  Performer
                                                  WirelessUnit
```

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│ User (Technician/Admin)                                   │
│  - title, role_description                               │
│  - belongsto: MonitoringGroup (M2M)                       │
│                                                           │
│  Methods:                                                 │
│  - get_monitoring_groups()                                │
│  - get_accessible_performers()  [via MonitoringGroup]    │
│  - get_accessible_devices()     [via MonitoringGroup]    │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │ MonitoringGroup                       │
        │ (Role-Based Access Control)           │
        │  - users (M2M)                        │
        │  - assignments                        │
        └──────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ PerformerAssignment                                       │
│  - performer (FK)                                         │
│  - wireless_unit (FK)                                     │
│  - monitoring_group (FK)                                  │
│  - alert_on_battery_low: bool                             │
│  - alert_on_signal_loss: bool                             │
│  - alert_on_audio_low: bool                               │
│  - alert_on_device_offline: bool                          │
│  - priority: low/normal/high/critical                     │
│  - is_active: bool                                        │
│  - assigned_by: User (FK)                                 │
│  - notes: str                                             │
│  - assigned_at, updated_at: datetime                      │
│                                                           │
│  Unique: (performer, wireless_unit)                       │
└──────────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
    ┌─────────────┐        ┌──────────────────┐
    │ Performer   │        │ WirelessUnit     │
    │  - name     │        │  - name          │
    │  - title    │        │  - model         │
    │  - photo    │        │  - serial        │
    │  - email    │        │  - status        │
    │  - phone    │        │  - frequency     │
    │  - notes    │        │  - battery       │
    │  - is_active │        │  - is_active     │
    └─────────────┘        └──────────────────┘
```

## Migration Path (Legacy Support)

### Old Pattern (DeviceAssignment - DEPRECATED)

```python
# Legacy: User assigned to RFChannel directly
assignment = AssignmentService.create_assignment(
    user=tech_user,
    channel=rf_channel,
    alert_enabled=True
)
```

**Status:** Maintained for backwards compatibility only. Use `AssignmentService`.

### New Pattern (PerformerAssignment - RECOMMENDED)

```python
# New: Performer assigned to WirelessUnit through MonitoringGroup
assignment = PerformerAssignmentService.create_assignment(
    performer=performer,
    wireless_unit=unit,
    monitoring_group=group,
    priority="high",
    alert_enabled=True,
    assigned_by=tech_user
)
```

**Advantages:**
- Separates talent/device users (performers) from operators (users)
- Role-based access via MonitoringGroups
- Cleaner RBAC model
- Supports multi-unit assignments per performer
- Assignment audit trail

## Service Layer Summary

### PerformerService (CRUD)

| Method | Purpose |
|--------|---------|
| `create_performer()` | Create new performer |
| `update_performer()` | Update performer metadata |
| `delete_performer()` | Delete performer and assignments |
| `get_performer_by_id()` | Retrieve by ID |
| `get_performer_by_name()` | Retrieve by name |
| `get_all_performers()` | List all (with active filter) |
| `search_performers()` | Multi-field search |
| `deactivate_performer()` | Soft-delete |
| `reactivate_performer()` | Restore |
| `count_total_performers()` | Statistics |
| `get_performers_with_assignments()` | Filter active |

### PerformerAssignmentService (Assignment Logic)

| Method | Purpose |
|--------|---------|
| `create_assignment()` | Create performer-to-unit assignment |
| `update_assignment()` | Update alerts/priority/notes |
| `delete_assignment()` | Delete assignment |
| `get_performer_assignments()` | Get all for performer |
| `get_unit_assignments()` | Get all for wireless unit |
| `get_group_assignments()` | Get all for monitoring group |
| `get_assignments_needing_alerts()` | Filter alert-enabled |
| `update_alert_status()` | Bulk alert toggle |
| `count_total_assignments()` | Statistics |
| `count_assignments_with_alerts()` | Statistics |
| `deactivate_assignment()` | Soft-deactivate |
| `reactivate_assignment()` | Restore |

## Implementation Examples

### Example 1: Create and Assign Performer to Unit

```python
from micboard.services import PerformerService, PerformerAssignmentService

# Create performer
performer = PerformerService.create_performer(
    name="Alice Johnson",
    title="Drummer",
    email="alice@band.com",
    photo_file=photo
)

# Create assignment
assignment = PerformerAssignmentService.create_assignment(
    performer=performer,
    wireless_unit=mic_unit,
    monitoring_group=stage_group,
    priority="high",
    alert_enabled=True,
    assigned_by=tech_user
)
```

### Example 2: User Views Accessible Performers

```python
# Technician views performers in their assigned groups
user = User.objects.get(id=1)
accessible_performers = user.get_accessible_performers()
accessible_devices = user.get_accessible_devices()

# Result: Only performers/devices in user's MonitoringGroups
```

### Example 3: Query Assignments with Alerts

```python
# Get all assignments needing alert monitoring
alert_assignments = PerformerAssignmentService.get_assignments_needing_alerts(
    monitoring_group=stage_group
)

# Each assignment has performer, unit, alert settings, priority
for assignment in alert_assignments:
    print(f"{assignment.performer.name} on {assignment.wireless_unit}")
```

### Example 4: Deactivate Performer Assignment (Temporary)

```python
# Temporarily deactivate without deleting
PerformerAssignmentService.deactivate_assignment(assignment=assignment)

# Later, reactivate
PerformerAssignmentService.reactivate_assignment(assignment=assignment)
```

## Database Considerations

### New Models

1. **Performer**
   - Multi-tenant support (TenantOptimizedQuerySet)
   - Indexed on: name, is_active
   - Soft-delete via is_active flag

2. **PerformerAssignment**
   - Multi-tenant support (TenantOptimizedQuerySet)
   - Unique constraint: (performer, wireless_unit)
   - Indexed on: performer, wireless_unit, monitoring_group, is_active

### Queries Optimized

- `with_performer_and_unit()` - Prefetch related objects
- `active()` - Filter is_active=True
- `by_monitoring_group()` - Group filtering
- `needing_alerts()` - Alert-enabled filtering

## Migration Notes

No database migration is required initially, as this is a new feature alongside existing DeviceAssignment. To migrate existing data:

1. Create performers from existing users/devices
2. Map DeviceAssignment → PerformerAssignment records
3. Gradually redirect views/APIs to new service layer
4. Deprecate DeviceAssignment over time

## Next Steps

1. Create/update serializers for Performer and PerformerAssignment
2. Create ViewSets for performer CRUD and assignment management
3. Update Alert model to reference PerformerAssignment
4. Create frontend UI for performer management
5. Create management commands for bulk operations
6. Add comprehensive tests
