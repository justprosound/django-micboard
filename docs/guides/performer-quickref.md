# Performer Assignment Quick Reference

Performers are the people using wireless units. They are separate from Django users, who are the operators managing those assignments.

## Imports

Import models and services from their defining modules:

```python
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
```

The root `micboard.models` and `micboard.services` packages do not re-export domain objects.

## Create a performer

Performer CRUD is available through the tenant-scoped Django admin. Application workflows should use `Performer.objects.for_user(user=request.user)` for reads and `PerformerAssignmentService` for every device binding; there is no unscoped performer facade.

## Create an assignment

All assignment writes require the acting user and object IDs. The service resolves every object through that user's scope before writing:

```python
from micboard.services.core.performer_assignment_dtos import CreatePerformerAssignment

assignment = PerformerAssignmentService.create_assignment(
    command=CreatePerformerAssignment(
        performer_id=performer_id,
        unit_id=wireless_unit.id,
        group_id=monitoring_group.id,
        priority="high",
        notes="Lead microphone",
        alert_on_battery_low=True,
        alert_on_signal_loss=True,
        alert_on_audio_low=False,
        alert_on_hardware_offline=True,
    ),
    user=request.user,
)
```

In MSP mode, the user must have an active `operator`, `admin`, or `owner` membership covering the unit's organization and campus. `viewer` memberships are read-only. References outside the user's monitoring-group or tenant scope raise `PermissionDenied`.

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

Use `for_user()` at request and task boundaries. In single-tenant mode, an unassigned performer is visible so an operator can create its first assignment. In MSP mode, a performer without a tenant-scoped assignment fails closed.

## Update or remove an assignment

```python
from micboard.services.core.performer_assignment_dtos import UpdatePerformerAssignment

assignment = PerformerAssignmentService.update_assignment(
    command=UpdatePerformerAssignment(
        assignment_id=assignment.id,
        priority="critical",
        alert_on_audio_low=True,
    ),
    user=request.user,
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

`deactivate_assignment()` preserves history. `delete_assignment()` permanently removes the row. Both return `False` when the scoped assignment does not exist.

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

Use `PerformerAssignment.objects.needing_alerts()` to select active assignments with at least one supported alert flag enabled.

## Data constraints

- A performer and wireless unit can have only one assignment row.
- A monitoring group owns the operational scope of an assignment.
- `assigned_by` records the user who created the assignment.
- Deactivated rows remain queryable but are excluded by `.active()`.

For the complete design and security boundaries, see [Performer Assignment Architecture](performer-assignment-architecture.md).