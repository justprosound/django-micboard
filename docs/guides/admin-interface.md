# Admin interface

django-micboard registers its operational models with Django admin. Available modules depend on
installed optional packages and enabled multitenancy settings.

## Access and tenant scope

Open `/admin/` in the host project. Users need Django staff status plus the model permission for
each operation. Object lists, object lookups, related-field choices, and bulk actions use the same
tenant/site scope; knowing another tenant's primary key does not grant access.

Organization, Campus, and Organization Membership administration is restricted to superusers.
Use narrow permissions for operational staff and verify custom admin extensions preserve
`MicboardModelAdmin` scoping.

## Inventory

Key model changelists use Django's normal app/model path pattern:

- `/admin/micboard/wirelesschassis/`: stationary receiver/transmitter/transceiver chassis
- `/admin/micboard/wirelessunit/`: handheld/bodypack/IEM field units
- `/admin/micboard/rfchannel/`: chassis RF channels
- `/admin/micboard/charger/` and `/admin/micboard/chargerslot/`: charger inventory
- `/admin/micboard/location/`: physical locations
- `/admin/micboard/monitoringgroup/`: monitoring groups

Prefer Django's `reverse("admin:micboard_wirelesschassis_changelist")` form in code instead of
hard-coding these paths.

## Location management

Locations and monitoring groups define inventory placement and tenant/site scope. Configure
locations before assigning chassis or chargers, and preserve the active scope when selecting
related objects.

## Discovery and approval

Discovery candidates live at `/admin/micboard/discovereddevice/`. Approval actions delegate to
the discovery approval service, which validates permissions and identity conflicts before
promoting candidates into inventory.

Configuration/status models include:

- `/admin/micboard/discoverycidr/`
- `/admin/micboard/discoveryfqdn/`
- `/admin/micboard/discoveryjob/`
- `/admin/micboard/discoveryqueue/`
- `/admin/micboard/devicemovementlog/`

Run discovery synchronization from the host environment:

```bash
uv run --no-sync python manage.py sync_discovery --manufacturer shure
```

Only use `--scan-cidrs` after reviewing configured ranges and bounding `--max-hosts`.

## Manufacturers and API servers

- `/admin/micboard/manufacturer/`: enable manufacturers and inspect plugin identity
- `/admin/micboard/manufacturerapiserver/`: location-specific API endpoints and credentials
- `/admin/micboard/manufacturerconfiguration/`: structured manufacturer configuration
- `/admin/micboard/configurationauditlog/`: redacted configuration history

Shared keys are write-only/masked in admin. Connection tests send each row's own credential, not a
global fallback. The endpoint hostname must appear exactly in
`MICBOARD_API_SERVER_ALLOWED_HOSTS`; entries do not accept schemes, ports, paths, or wildcards.

## Settings

Setting definitions and scoped values are available at:

- `/admin/micboard/settingdefinition/`
- `/admin/micboard/setting/`

The app also mounts authenticated settings overview/edit routes under its configured URL prefix.
Definitions declare their allowed scope, and forms reject a value targeted at another scope.
Sensitive values render masked.

## Assignments and alerts

- `/admin/micboard/performer/`
- `/admin/micboard/performerassignment/`
- `/admin/micboard/useralertpreference/`
- `/admin/micboard/alert/`

Assignment logic belongs in the performer-assignment service; admin remains a thin request
adapter.

## Real-time and audit status

Real-time connection records are at `/admin/micboard/realtimeconnection/`. Inspect the same state
from the command line:

```bash
uv run --no-sync python manage.py realtime_status --verbose
```

Operational history is available through Activity Log, Service Sync Log, Device Movement Log, and
Configuration Audit Log admins. Activity and service-sync history is view-only; retention services
own deletion. Secret-bearing configuration is redacted in audit displays.

## Bulk actions

Admin actions run only against the already-scoped queryset. Chassis refresh carries the exact
selected IDs to the service/task rather than widening selection in background work. Lifecycle
side effects and real-time broadcasts are scheduled after successful transaction commit.

Review action confirmation pages before applying status, approval, or delete operations.

## Troubleshooting

### An object is missing

- Confirm the user has the model's view permission.
- Confirm the object belongs to the active site/organization scope.
- Confirm the model's optional dependency is installed when applicable.
- Use a superuser only to diagnose policy, not as the permanent workaround.

### Connection test is denied

- Add the exact endpoint hostname to `MICBOARD_API_SERVER_ALLOWED_HOSTS`.
- Keep the URL on HTTPS and install its issuing CA.
- Confirm the row has its own shared key.

### Admin pages are slow

- Capture query counts for the concrete changelist.
- Preserve existing `select_related`/`prefetch_related` behavior in overrides.
- Avoid per-row service/API calls in `list_display` methods.

### Real-time state is stale

```bash
uv run --no-sync python manage.py realtime_status --verbose
uv run --no-sync python manage.py poll_devices --manufacturer shure
```

If synchronous polling succeeds but queued work does not, inspect the native Huey consumer and
backend connectivity.
