---
title: "Monitor devices"
type: how-to
audience: staff
---
Operate and check live monitoring of a running django-micboard deployment: polling, subscription supervisors, health checks, and the read-only REST API.

## What is monitored

Each polled chassis and wireless unit records battery level and health, RF level, audio level, status, and last-seen time. Open the Django admin at `/admin/` for the inventory, or the dashboard pages mounted from `micboard.urls`. Pages refresh by HTTP polling by default. WebSocket push is opt-in: see [Real-time updates](realtime-updates.md).

## Poll devices

Run a one-shot poll directly or enqueue it through native Huey:

```bash
# Poll Shure devices now
uv run --no-sync python manage.py poll_devices --manufacturer shure

# Enqueue one poll through native Huey
uv run --no-sync python manage.py poll_devices --manufacturer shure --async
```

Use your deployment scheduler to enqueue the one-shot command at the required interval. Polling refuses an inactive manufacturer. To poll one anyway as an operator, add `--force`; the override is preserved when the command enqueues Huey work.

After a manufacturer poll, Micboard evaluates alerts for active assigned wireless units in primary
key order. `MICBOARD_POLL_ALERT_MAX_UNITS` limits each scan (default: 100, hard maximum: 500).
Three additional top-level Django settings bound fanout within that scan:
`MICBOARD_POLL_ALERT_MAX_ASSIGNMENTS` (default: 100, hard maximum: 500),
`MICBOARD_POLL_ALERT_MAX_RECIPIENTS` (default: 250, hard maximum: 1,000), and
`MICBOARD_POLL_ALERT_MAX_DELIVERIES` (default: 250, hard maximum: 1,000). Micboard rotates shared
cache cursors through bounded pages so later units, assignments, and recipients are not permanently
starved. Inactive assignments, monitoring groups, and users are excluded. Recipient membership and
tenant scope are revalidated immediately before alert persistence and again before email delivery,
so deactivation or reassignment during a poll fails closed. A cache outage falls back to the first
bounded page and never disables alert evaluation.

Polling does not start realtime subscription supervisors. Launch one per manufacturer as a
separate foreground process; the integration decides its own transport:

```bash
# Shure
uv run --no-sync python manage.py realtime_subscribe --manufacturer shure

# Sennheiser
uv run --no-sync python manage.py realtime_subscribe --manufacturer sennheiser
```

Hosts that schedule through native Huey should explicitly enqueue the registered
`start_realtime_subscriptions` entrypoint once per manufacturer. Multi-process
deployments require a process-shared Django cache for the singleton lease. A stopped or crashed
supervisor may take up to 60 seconds to become eligible for restart. See
[Real-time Updates](realtime-updates.md#run-subscription-supervisors) for limits and settings.

## Check connection health

```bash
# Check all connections
uv run --no-sync python manage.py realtime_status

# Check specific manufacturer
uv run --no-sync python manage.py realtime_status --manufacturer shure
```

## Alerts

After every manufacturer poll, alerts are evaluated for active assigned units. The thresholds that trigger them, such as `battery_low_level`, are [settings](settings-management.md). Per-assignment alert switches (`alert_on_battery_low`, `alert_on_signal_loss`, `alert_on_audio_low`, `alert_on_hardware_offline`) are set when you create or update an assignment.

## Assign a unit to a performer

```python
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import CreatePerformerAssignment

# Assign a wireless unit to a performer
assignment = PerformerAssignmentService.create_assignment(
    command=CreatePerformerAssignment(
        performer_id=performer.id,
        unit_id=wireless_unit.id,
        group_id=monitoring_group.id,
        alert_on_battery_low=True,
    ),
    user=user,
)
```

## Read locations

Read locations through the authenticated monitoring scope. Create, update, and assign locations
through the permission-checked Django admin:

```python
from micboard.models.locations.structure import Location
from micboard.services.shared.visibility import visible_to

locations = visible_to(Location, user=request.user).filter(is_active=True)
```

## Troubleshooting

### Device Not Updating

**Check connection status:**
```bash
uv run --no-sync python manage.py realtime_status --manufacturer shure
```

**Verify API access:**
```bash
uv run --no-sync python manage.py diagnostic_api_health_check
```

**Check the manufacturer side:** confirm the Shure System API is reachable from the host. See [Shure troubleshooting](shure-troubleshooting.md).

### WebSocket Issues

**Test WebSocket connection:**
- Open browser developer tools
- Check Network tab for WebSocket connections
- Verify ASGI configuration

**Redis connection:**
```bash
# Test Redis connectivity
uv run --no-sync python manage.py shell -c "from channels.layers import get_channel_layer; print(get_channel_layer())"
```

### Performance Issues

**Monitor polling performance:**
```bash
# Run one poll and inspect its completion summary
uv run --no-sync python manage.py poll_devices --manufacturer shure
```


## Read monitoring state over HTTP

The read-only REST API under `api/v1/` (relative to where you mount `micboard.urls`) exposes `chassis`, `units`, `channels`, `discovery`, `monitoring/groups`, `monitoring/alerts`, `settings/definitions` and `settings/overrides`. It requires an authenticated user and returns only rows that user may see. See [HTTP endpoints](../api/endpoints.md).

## Summarize connection health in code

```python
from micboard.services.realtime.health_service import RealtimeConnectionHealthService

# Returns one bounded, typed status aggregate.
summary = RealtimeConnectionHealthService.summarize()
print(f"Active real-time connections: {summary.connected}")
```
