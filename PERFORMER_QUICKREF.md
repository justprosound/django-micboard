# Performer Assignment Quick Reference

Performers are the people using wireless units. They are separate from Django users, who are
the operators managing those assignments.

## Imports

Import models and services from their defining modules:

```python
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer import PerformerService
from micboard.services.core.performer_assignment import PerformerAssignmentService
```

The root `micboard.models` and `micboard.services` packages do not re-export domain objects.

## Create a performer

```python
performer = PerformerService.create_performer(
    name="Jane Smith",
    title="Lead vocalist",
    email="jane@example.com",
    role_description="Primary vocal microphone",
    notes="Prefers a handheld transmitter",
)
```

Photos are model fields rather than service arguments. Assign a photo to the returned instance
and save it with Django's normal file-field API when needed.

## Create an assignment

All assignment writes require the acting user and object IDs. The service resolves every object
through that user's scope before writing:

```python
assignment = PerformerAssignmentService.create_assignment(
    performer_id=performer.id,
    unit_id=wireless_unit.id,
    group_id=monitoring_group.id,
    user=request.user,
    priority="high",
    notes="Lead microphone",
    alert_on_battery_low=True,
    alert_on_signal_loss=True,
    alert_on_audio_low=False,
    alert_on_hardware_offline=True,
)
```

In MSP mode, the user must have an active `operator`, `admin`, or `owner` membership covering the
unit's organization and campus. `viewer` memberships are read-only. References outside the user's
monitoring-group or tenant scope raise `PermissionDenied`.

## Read scoped assignments

```python
assignments = (
    PerformerAssignment.objects.for_user(user=request.user)
    .active()
    .with_performer_and_unit()
)

performers = Performer.objects.for_user(user=request.user).active()
units = WirelessUnit.objects.for_user(user=request.user)
```

Use `for_user()` at request and task boundaries. In single-tenant mode, an unassigned performer is
visible so an operator can create its first assignment. In MSP mode, a performer without a
tenant-scoped assignment fails closed.

## Update or remove an assignment

```python
assignment = PerformerAssignmentService.update_assignment(
    assignment_id=assignment.id,
    user=request.user,
    priority="critical",
    alert_on_audio_low=True,
)

was_deactivated = PerformerAssignmentService.deactivate_assignment(
    assignment_id=assignment.id,
    user=request.user,
)

was_deleted = PerformerAssignmentService.delete_assignment(
    assignment_id=assignment.id,
    user=request.user,
)
```

`deactivate_assignment()` preserves history. `delete_assignment()` permanently removes the row.
Both return `False` when the scoped assignment does not exist.

## Alert preferences

Alert preferences are independent flags on each assignment:

```python
preferences = {
    "battery_low": assignment.alert_on_battery_low,
    "signal_loss": assignment.alert_on_signal_loss,
    "audio_low": assignment.alert_on_audio_low,
    "hardware_offline": assignment.alert_on_hardware_offline,
}
# {
#     "battery_low": True,
#     "signal_loss": True,
#     "audio_low": False,
#     "hardware_offline": True,
# }
```

Use `PerformerAssignment.objects.needing_alerts()` to select active assignments with at least one
supported alert flag enabled.

## Data constraints

- A performer and wireless unit can have only one assignment row.
- A monitoring group owns the operational scope of an assignment.
- `assigned_by` records the user who created the assignment.
- Deactivated rows remain queryable but are excluded by `.active()`.

For the complete design and security boundaries, see
[`micboard/docs/PERFORMER_ASSIGNMENT_ARCHITECTURE.md`](micboard/docs/PERFORMER_ASSIGNMENT_ARCHITECTURE.md).
