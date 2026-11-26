---
title: "HTTP endpoints"
type: reference
audience: developer
---
django-micboard ships HTML/HTMX pages and a read-only REST API. Mount both from the host project:

```python
from django.urls import include, path

urlpatterns = [
    path("micboard/", include("micboard.urls")),
]
```

Use Django's `reverse()` with the `micboard` namespace rather than hard-coding paths. The routes are defined in `micboard/urls.py`.

## REST API v1

Mounted at `api/v1/` under the include above, with the `micboard:api_v1` namespace. Every viewset is a Django REST Framework `ReadOnlyModelViewSet`: only `GET`, `HEAD` and `OPTIONS` are served. Every request must be authenticated, and the queryset is limited to rows the user may see (`micboard/services/shared/visibility.py::visible_to`). Serializers live in `micboard/serializers/v1/`; pagination and throttling come from the host project's DRF settings.

| Path | Resource |
| --- | --- |
| `chassis/` | Wireless chassis |
| `units/` | Wireless units |
| `channels/` | RF channels |
| `discovery/` | Discovered devices |
| `monitoring/groups/` | Monitoring groups |
| `monitoring/alerts/` | Alerts |
| `settings/definitions/` | Setting definitions |
| `settings/overrides/` | Stored setting values |

Each collection has a detail route (`<id>/`) and the DRF API root lists them.

## Dashboard and HTMX pages

| Name | Path |
| --- | --- |
| `micboard:index`, `about` | `/`, `about/` |
| `micboard:alerts`, `alert_rows`, `alert_detail`, `acknowledge_alert`, `resolve_alert` | `alerts/`, `alerts/rows/`, `alerts/<id>/`, `alerts/<id>/acknowledge/`, `alerts/<id>/resolve/` |
| `micboard:charger_dashboard`, `charger_grid` | `chargers/`, `chargers/grid/` |
| `micboard:all_buildings_view`, `single_building_view`, `rooms_in_building_view` | `buildings/`, `buildings/<id>/receivers/`, `buildings/<id>/rooms/` |
| `micboard:all_rooms_view`, `room_view` | `rooms/`, `rooms/<id>/receivers/` |
| `micboard:device_type_view`, `priority_view`, `performer_view` | `device-type/<role>/`, `priority/<priority>/`, `performers/<id>/` |
| `micboard:assignments`, `assignment_rows`, `create_assignment`, `update_assignment`, `delete_assignment` | `assignments/`, `assignments/rows/`, `assignments/create/`, `assignments/<id>/update/`, `assignments/<id>/delete/` |
| `micboard:settings_overview`, `settings_bulk_config`, `settings_manufacturer_config`, `settings_diff` | `settings/`, `settings/bulk/`, `settings/manufacturer/`, `settings-diff/` |
| `micboard:display_wall_list`, `display_wall_detail`, `wall_section_list`, `kiosk_data`, `kiosk_content`, `kiosk_health` | `walls/`, `walls/<id>/`, `walls/<id>/sections/`, `walls/<id>/data/`, `walls/<id>/content/`, `walls/<id>/health/` |
| `micboard:kiosk_display` | `kiosk/<kiosk_id>/` |

Admin pages use the host project's `admin:` namespace.

## WebSocket

For authenticated real-time events, see the [WebSocket API](websocket.md).
