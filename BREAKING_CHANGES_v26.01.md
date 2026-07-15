# Breaking Changes - django-micboard v26.01.27+

## URL Namespace Addition (CRITICAL)

### What Changed
All django-micboard URLs now require the `micboard:` namespace prefix for proper isolation in host projects.

### Why This Change
Without namespace, generic URL names like `index`, `about`, `alerts` can collide with host project URLs, causing routing conflicts and hard-to-debug issues.

### Migration Required
**All existing projects using django-micboard must update URL references.**

---

## Python Code Changes

### Before (❌ Will Break)
```python
from django.urls import reverse

# These will raise NoReverseMatch errors
redirect_url = reverse("index")
alert_url = reverse("alerts")
room_url = reverse("room_view", kwargs={"room_id": 101})
```

### After (✅ Correct)
```python
from django.urls import reverse

# Add 'micboard:' prefix to all app URLs
redirect_url = reverse("micboard:index")
alert_url = reverse("micboard:alerts")
room_url = reverse("micboard:room_view", kwargs={"room_id": 101})
```

### Quick Fix Command
```bash
# Find all Python files with micboard reverse() calls
rg -n 'reverse\("(index|alerts|about|room_view|single_building_view)' --glob '*.py'
```

---

## Template Changes

### Before (❌ Will Break)
```django
{# Navigation links #}
<a href="{% url 'index' %}">Dashboard</a>
<a href="{% url 'alerts' %}">Alerts</a>
<a href="{% url 'all_rooms_view' %}">Rooms</a>

{# Form actions #}
<form action="{% url 'create_assignment' %}" method="post">

{# HTMX endpoints #}
<div hx-get="{% url 'assignment_rows' %}" hx-trigger="every 5s">
```

### After (✅ Correct)
```django
{# Navigation links #}
<a href="{% url 'micboard:index' %}">Dashboard</a>
<a href="{% url 'micboard:alerts' %}">Alerts</a>
<a href="{% url 'micboard:all_rooms_view' %}">Rooms</a>

{# Form actions #}
<form action="{% url 'micboard:create_assignment' %}" method="post">

{# HTMX endpoints #}
<div hx-get="{% url 'micboard:assignment_rows' %}" hx-trigger="every 5s">
```

### Quick Fix Command
```bash
# Find all templates with micboard URL tags
rg -n "{% url" --glob '*.html'
```

---

## Complete URL Reference

All these URL names now require the `micboard:` prefix:

### Dashboard & Navigation
- `micboard:index` - Main dashboard
- `micboard:about` - About page
- `micboard:alerts` - Alerts list
- `micboard:alert_rows` - Filtered alert table fragment

### View Modes
- `micboard:all_buildings_view` - All buildings
- `micboard:single_building_view` - Chassis in one building by integer ID
- `micboard:rooms_in_building_view` - Rooms in one building by integer ID
- `micboard:all_rooms_view` - All visible rooms
- `micboard:room_view` - Chassis in one room by integer ID
- `micboard:performer_view` - Chassis assigned to one performer by integer ID
- `micboard:device_type_view` - Chassis by validated RF role
- `micboard:priority_view` - Chassis by validated assignment priority

### Charger Management
- `micboard:charger_display` - Charger display
- `micboard:charger_dashboard` - Charger dashboard

### Assignments
- `micboard:assignments` - List assignments
- `micboard:assignment_rows` - Assignment table fragment
- `micboard:create_assignment` - Create assignment
- `micboard:update_assignment` - Update assignment
- `micboard:delete_assignment` - Delete assignment

### Alerts
- `micboard:alert_detail` - Alert detail view
- `micboard:acknowledge_alert` - Acknowledge alert action
- `micboard:resolve_alert` - Resolve alert action

### Kiosk Mode
- `micboard:kiosk_display` - Kiosk authentication and display entry point
- `micboard:kiosk_data` - Kiosk data view
- `micboard:kiosk_content` - Kiosk content fragment
- `micboard:kiosk_health` - Kiosk health check
- `micboard:display_wall_list` - Display wall list
- `micboard:display_wall_detail` - Display wall detail
- `micboard:wall_section_list` - Wall section list

### Partials (HTMX)
- `micboard:channel_card_partial` - Channel card
- `micboard:device_tiles_partial` - Device tiles
- `micboard:charger_grid_partial` - Charger grid
- `micboard:charger_slot_partial` - Charger slot
- `micboard:wall_section_partial` - Wall section
- `micboard:alert_row_partial` - Alert row
- `micboard:assignment_row_partial` - Assignment row

---

## Admin URLs (No Changes Required)

Admin URLs continue to use the `admin:` namespace and are **NOT affected** by this change:

```python
# These continue to work as-is (no changes needed)
reverse("admin:index")
reverse("admin:micboard_manufacturer_changelist")
reverse("admin:micboard_wirelesschassis_change", args=[chassis_id])
```

Templates using admin URLs also work unchanged:
```django
{% url 'admin:index' %}
{% url 'admin:micboard_manufacturer_changelist' %}
```

---

## Testing Your Migration

### 1. Check for Missing Namespace
Start your Django development server and access the app:
```bash
uv run --no-sync python manage.py runserver
```

Visit `http://localhost:8000/micboard/` and click through all navigation links. If you see `NoReverseMatch` errors, you have URLs that need the namespace prefix.

### 2. Search Your Codebase
```bash
# Python files: Look for reverse() calls
rg -n "reverse\(" --glob '*.py'

# Templates: Look for {% url %} tags
rg -n "{% url" --glob '*.html'
```

### 3. Run Django's URL Check
```bash
# Verify all URL patterns resolve correctly
uv run --no-sync python manage.py check --deploy
```

### 4. Run Your Test Suite
```bash
# URL-related tests should catch missing namespaces
uv run --no-sync pytest
```

---

## Common Error Messages

### NoReverseMatch Error
```
django.urls.exceptions.NoReverseMatch: Reverse for 'index' not found.
'index' is not a valid view function or pattern name.
```

**Solution:** Add `micboard:` prefix to the URL name:
```python
# Change this:
reverse("index")
# To this:
reverse("micboard:index")
```

### Template NoReverseMatch
```
django.urls.exceptions.NoReverseMatch: Reverse for 'alerts' not found.
```

**Solution:** Add `micboard:` prefix in template:
```django
{# Change this: #}
{% url 'alerts' %}
{# To this: #}
{% url 'micboard:alerts' %}
```

---

## Verification Checklist

After migration, verify these work:

- [ ] Dashboard loads at `/micboard/`
- [ ] Navigation bar links work (Dashboard, Alerts, About)
- [ ] View dropdown menu works (By Building, By Room, etc.)
- [ ] Alert list and detail pages load
- [ ] Assignment creation/editing works
- [ ] Charger dashboard displays correctly
- [ ] HTMX live updates continue working
- [ ] Kiosk mode displays function
- [ ] Forms submit to correct URLs
- [ ] Breadcrumbs and back links work

---

## Need Help?

If you encounter issues during migration:

1. **Check the logs:** Look for `NoReverseMatch` errors in Django output
2. **Search your code:** Use the commands above to find all URL references
3. **Verify URL names:** Compare against the "Complete URL Reference" section
4. **File an issue:** https://github.com/justprosound/django-micboard/issues

---

## Configuration Access Pattern

Direct Django settings reads and the former app-config cache are unsupported:

```python
# Removed patterns
from django.conf import settings
config = getattr(settings, "MICBOARD_CONFIG", {})
from micboard.apps import MicboardConfig
config = MicboardConfig.get_config()
```

To:

```python
# Canonical pattern
from micboard.services.settings.settings_service import settings as micboard_settings
config = micboard_settings.get_config_dict()
```

All Micboard runtime configuration reads now use the canonical settings service.

---

**Last Updated:** 2026-01-28
**Applies to:** django-micboard v26.01.27 and later
**Migration Time:** ~15-30 minutes for typical projects
