# Python and integration reference

django-micboard is a reusable Django app. Its stable integration surface is the typed service
layer, management commands, model managers, and authenticated WebSocket consumer. A general REST
API is not shipped yet; see [HTTP endpoints](../api/endpoints.md) for current status.

## Hardware queries

Use the models' user-scoped managers instead of exposing an unscoped queryset:

```python
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit

active_chassis = WirelessChassis.objects.for_user(user=request.user).active()
active_units = WirelessUnit.objects.for_user(user=request.user).active()
```

Never trust tenant IDs supplied by clients; derive access from the authenticated user.

## Performer assignments

Assignment writes go through the service so object scope and role checks stay centralized:

```python
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import CreatePerformerAssignment

assignment = PerformerAssignmentService.create_assignment(
    command=CreatePerformerAssignment(
        performer_id=performer.id,
        unit_id=wireless_unit.id,
        group_id=monitoring_group.id,
        alert_on_battery_low=True,
    ),
    user=request.user,
)
```

## Manufacturer integrations

Resolve plugins through the registry:

```python
from micboard.services.manufacturer.plugin_registry import PluginRegistry

plugin = PluginRegistry.get_plugin("shure")
if plugin is not None:
    devices = plugin.get_devices()
```

The Shure HTTP client is also available for integration-specific operations:

```python
from micboard.integrations.shure.client import ShureSystemAPIClient

client = ShureSystemAPIClient()
devices = client.devices.get_devices()
health = client.check_health()
```

## WebSocket updates

The browser WebSocket endpoint is `/ws` and requires authentication. Configure the host ASGI
application with `AllowedHostsOriginValidator` around `AuthMiddlewareStack`; see the
[real-time guide](../guides/realtime-updates.md).

## Management commands

Poll a manufacturer once:

```bash
uv run --no-sync python manage.py poll_devices --manufacturer shure
```

Add `--async` to enqueue the poll through native Huey. Inspect command-specific options without
running work:

```bash
uv run --no-sync python manage.py poll_devices --help
uv run --no-sync python manage.py diagnostic_api_health_check --help
```

## Rate limiting

External manufacturer calls use the shared rate limiter and retry infrastructure. See the
[integration reference](../integration/integration-references.md#shared-rate-limiter).
