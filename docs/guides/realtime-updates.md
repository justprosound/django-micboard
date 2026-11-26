---
title: "Set up real-time updates"
description: "Choose between HTTP polling and WebSocket push, wire the ASGI application, and run subscription supervisors."
type: how-to
audience: developer
---
django-micboard gets updates in front of people in two ways, and a deployment chooses between them.

**HTTP polling is the default.** Alerts, assignments, the charger grid and kiosk walls refresh themselves with a short request on a timer. Nothing needs configuring. The intervals are settings (`REFRESH_INTERVAL_*`, see [Configuration](../configuration.md)).

**WebSocket push is opt-in.** The app ships an authenticated consumer and its routing, but no browser client. A host project supplies the client and wires the ASGI application below. Until it does, every surface keeps polling. The `micboard.W002` and `micboard.W003` system checks report a half-wired setup. The message contract is in the [WebSocket API](../api/websocket.md).

## Configure Channels and ASGI

**settings.py:**
```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}
```

**asgi.py:**
```python
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_project.settings")
django_asgi_app = get_asgi_application()

from micboard.websockets.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
```

## Keep a connection alive

Micboard sends nothing on a quiet connection, so a reverse proxy that closes idle upstream
connections will close a healthy one. The client drives the keepalive:

```javascript
// Client heartbeat. The command key is `command`, not `type`.
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({command: 'ping'}));
    }
}, 30000);
```

Micboard replies `{"type": "pong"}`. Choose an interval comfortably shorter than your proxy's
idle timeout and comfortably under `MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE` (default 60):
a connection that exceeds its command allowance is closed with code `4429`. See
[Installation](../installation.md) for the matching nginx and Traefik timeouts.

## Run subscription supervisors

Subscription supervisors are explicit long-running processes. Polling never starts or enqueues a
supervisor. One command drives both transports — the manufacturer's integration declares whether
it streams over a WebSocket or SSE — and it runs in the foreground until the subscriptions end or
the process is interrupted, so run it under your normal process supervisor:

```bash
# Shure, which streams over a per-receiver WebSocket
uv run --no-sync python manage.py realtime_subscribe --manufacturer shure

# Sennheiser, which streams over an SSCv2 SSE subscription
uv run --no-sync python manage.py realtime_subscribe --manufacturer sennheiser

# Optional single-device diagnostic selection
uv run --no-sync python manage.py realtime_subscribe \
  --manufacturer sennheiser --device DEVICE_ID
```

For queue-managed deployments, Micboard registers `start_realtime_subscriptions` as a native Huey
task entrypoint. The host deployment or scheduler must explicitly enqueue it once per
manufacturer; recurring device polls do not do so. These long-running tasks consume a Huey worker
slot, so reserve worker capacity accordingly.

Every invocation uses the same renewable singleton lease, keyed by transport and manufacturer. A deployment with more
than one process must point `MICBOARD_REALTIME_CACHE_ALIAS` (default: `"default"`) at a
process-shared Django cache. A local-memory cache only deduplicates inside one process. The
following settings bound each supervisor:

- `MICBOARD_REALTIME_MAX_DEVICES`: 64 by default, hard-capped at 256.
- `MICBOARD_REALTIME_MAX_CONCURRENCY`: 16 by default, hard-capped at 64 and never greater than the
  device limit.
- `MICBOARD_REALTIME_ROTATION_SECONDS`: 300 by default, hard-capped at 3,600. A long-lived
  connection is cancelled after its turn so a fixed worker cannot starve later selected devices.
- `MICBOARD_REALTIME_RECONNECT_DELAY_SECONDS`: 1 by default, hard-capped at 60. This pause applies
  between repeated connection rounds.

Each supervisor uses at most the configured concurrency count of worker tasks. Inventory selection
uses a shared-cache circular primary-key cursor. Each completed connection round reloads the next
bounded window under the same lease, and restarts resume from the persisted cursor. Point the cache
alias at process-shared storage to preserve this fairness across workers. Explicit single-device
diagnostics do not advance that cursor.

The lease is renewed every 15 seconds. After a crash or clean stop, wait up to 60 seconds before
restarting the same transport. Micboard deliberately lets the token expire because Django's
generic cache API cannot safely compare and delete a lease owned by a particular process.

## Load an initial snapshot

The bundled `MicboardConsumer` handles authenticated WebSocket updates. Use the user-scoped
manager when a view needs an initial snapshot:

```python
from micboard.services.shared.visibility import visible_to
from micboard.models.hardware.wireless_chassis import WirelessChassis

chassis = visible_to(WirelessChassis, user=request.user).filter(
    status__in=("online", "degraded", "provisioning"),
)
snapshot = list(chassis.values("id", "name", "status"))
```

## Debug a connection

- In the browser developer tools, the Network tab lists WebSocket connections and their frames.
- A close code of `4401` means the user is not authenticated, `4403` means authenticated but not authorized, and `4429` means the connection exhausted its command allowance.
- If the socket never connects, check the ASGI application, that the channel layer backend (for example Redis) is running, and the proxy's WebSocket and idle timeouts. See [Installation](../installation.md).
- If updates do not arrive, confirm that a subscription supervisor or poll is running: `uv run --no-sync python manage.py realtime_status`.
