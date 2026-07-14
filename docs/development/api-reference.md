# Python and integration reference

django-micboard is a reusable Django app. Its stable integration surface is the typed service
layer, management commands, model managers, and authenticated WebSocket consumer. A general REST
API is not shipped yet; see [HTTP endpoints](../api/endpoints.md) for current status.

## Hardware queries

Use the query service instead of exposing an unscoped model queryset:

```python
from micboard.services.core.hardware_query import HardwareQueryService

active_chassis = HardwareQueryService.get_active_chassis(
    organization_id=organization_id,
    campus_id=campus_id,
)
active_units = HardwareQueryService.get_active_units(
    organization_id=organization_id,
    campus_id=campus_id,
)
```

In request-facing code, derive tenant identifiers from authenticated middleware context or use a
model manager's `for_user(user=request.user)` method. Do not trust tenant IDs supplied by clients.

## Performer assignments

Assignment writes go through the service so object scope and role checks stay centralized:

```python
from micboard.services.core.performer_assignment import PerformerAssignmentService

assignment = PerformerAssignmentService.create_assignment(
    performer_id=performer.id,
    unit_id=wireless_unit.id,
    group_id=monitoring_group.id,
    user=request.user,
    alert_on_battery_low=True,
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
application with `AuthMiddlewareStack`; see the [real-time guide](../guides/realtime-updates.md).

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
uv run --no-sync python manage.py device_discovery --help
```

## Rate limiting

External manufacturer calls use the shared rate limiter and retry infrastructure. See the
[integration reference](../integration/integration-references.md#shared-rate-limiter).
