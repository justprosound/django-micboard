---
title: "HTTP Endpoints"
---
django-micboard does not currently ship a general-purpose REST API. The reusable app exposes
HTML/HTMX views, authenticated kiosk-support JSON responses, and the service layer documented
below. A stable REST API remains tracked in
[GitHub issue #74](https://github.com/justprosound/django-micboard/issues/74).

## Host URL Configuration

Mount the app's URL configuration in the host project:

```python
from django.urls import include, path

urlpatterns = [
    path("micboard/", include("micboard.urls")),
]
```

The concrete routes and names are defined in `micboard.urls`. Use Django's `reverse()` rather
than hard-coding paths.

## Service-Layer Queries

Host-project views can build their own API using user-scoped model managers:

```python
from micboard.services.shared.visibility import visible_to
from micboard.models.hardware.wireless_chassis import WirelessChassis

chassis = visible_to(WirelessChassis, user=request.user).filter(
    status__in=("online", "degraded", "provisioning"),
)
payload = list(chassis.values("id", "name", "status"))
```

Apply authentication, authorization, pagination, throttling, and serialization in the host
project. Keep the authenticated `visible_to()` scope on every request-facing queryset.

## WebSocket API

For authenticated real-time events, see the [WebSocket API](websocket.md).
