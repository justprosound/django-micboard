# Performer Assignment Architecture

## Purpose

Performer assignments connect three existing records:

- a `Performer`, representing the person using equipment;
- a `WirelessUnit`, representing the assigned transmitter or microphone; and
- a `MonitoringGroup`, defining which operators can observe the assignment.

Django users are operators. Performers are domain records and are never authentication identities.

## Domain model

`PerformerAssignment` owns assignment state, priority, notes, per-condition alert preferences, and the `assigned_by` audit reference. The database permits only one row for a performer/wireless-unit pair. Deactivation preserves that row and its history.

The model manager provides composable query helpers:

- `for_user(user=...)` applies monitoring-group and tenant visibility;
- `active()` selects active assignments;
- `by_monitoring_group(group=...)` limits results to one group;
- `with_performer_and_unit()` loads the common relationship graph; and
- `needing_alerts(after=...)` selects active assignments with alerting enabled.

## Write boundary

Views, admin actions, and background tasks must send assignment writes through `PerformerAssignmentService`. Callers pass IDs and the acting user rather than pre-resolved model objects:

```python
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import CreatePerformerAssignment

assignment = PerformerAssignmentService.create_assignment(
    command=CreatePerformerAssignment(
        performer_id=performer.id,
        unit_id=wireless_unit.id,
        group_id=monitoring_group.id,
        priority="high",
        alert_on_battery_low=True,
        alert_on_signal_loss=True,
        alert_on_hardware_offline=True,
    ),
    user=request.user,
)
```

The service provides `create_assignment()`, `update_assignment()`, `deactivate_assignment()`, and `delete_assignment()`. This is deliberately a small API: scoped resolution, authorization, and lifecycle behavior stay in one place.

## Access-control invariants

Every write validates all referenced objects against the acting user:

1. The monitoring group must be active and assigned to the user, unless the user is a superuser.
2. The performer must be returned by `Performer.objects.for_user()`.
3. The wireless unit must be returned by `WirelessUnit.objects.for_user()`.
4. In MSP mode, the user needs an active `operator`, `admin`, or `owner` membership covering the unit's organization and campus.
5. Unsupported, tenantless, or cross-tenant relationships fail closed.

`viewer` memberships can read in-scope assignments but cannot create, change, deactivate, or delete them. Permission failures use Django's `PermissionDenied`; HTTP views translate that into a 403 response without exposing whether an out-of-scope object exists.

Superuser cross-organization access follows the host's `MICBOARD_ALLOW_CROSS_ORG_VIEW` setting.

## Read boundary

Request-facing reads begin with user-scoped managers:

```python
assignments = PerformerAssignment.objects.for_user(user=request.user)
performers = Performer.objects.for_user(user=request.user)
```

Single-tenant mode exposes an unassigned performer so its first assignment can be created. MSP mode cannot infer a safe tenant for an unassigned performer, so it remains hidden until the host provides a tenant-scoped relationship.

The assignment list view combines `for_user()` with `select_related()` for performer, wireless unit, and monitoring group. Services that need chassis/location details should use `with_performer_and_unit()` or an equivalent explicit relationship plan rather than triggering per-row queries.

## Alert preferences

Alert behavior is represented by four independent fields:

- `alert_on_battery_low`;
- `alert_on_signal_loss`;
- `alert_on_audio_low`; and
- `alert_on_hardware_offline`.

There is no aggregate `alert_enabled` service argument. Callers update only the conditions they want to change. Read the four explicit model fields when evaluating alert policy; there is no parallel dictionary representation to keep synchronized.

## Integration guidance

- Keep views and Huey tasks thin; they parse input and delegate to the service.
- Do not construct assignments directly from untrusted IDs.
- Do not re-export the models or service from root packages; import their defining modules.
- Use canonical queryset helpers for access checks instead of duplicating tenant predicates.
- Add access tests for different organizations, campuses, monitoring groups, and membership roles whenever assignment behavior changes.

See the repository-root [Performer Quickref](performer-quickref.md) for current call examples.