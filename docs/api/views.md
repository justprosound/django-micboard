# Views

The reusable app's request adapters live in `micboard.views` and serve HTML/HTMX dashboards,
settings pages, assignments, alerts, and authenticated kiosk-support responses. Concrete paths
and names are defined by `micboard.urls`; use Django's `reverse()` rather than hard-coding them.

django-micboard does not currently ship a general-purpose REST viewset package. Host projects
that add JSON endpoints should keep views thin, call domain services, authenticate every request,
and scope all objects before lookup or serialization.

See [HTTP endpoints](endpoints.md) and [WebSocket API](websocket.md) for supported integration
surfaces.
