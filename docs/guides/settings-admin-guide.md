---
title: "Configure settings in the admin"
description: "Set thresholds, intervals and feature switches for a manufacturer or organization in the Django admin."
type: how-to
audience: staff
---
Settings control things such as battery thresholds, polling intervals and API timeouts. Each setting definition applies at one scope: manufacturer, organization, site or global. The standard keys and defaults are listed in [Setting definitions reference](settings-quick-reference.md).

## Make sure the definitions exist

1. In the Django admin, open **Micboard > Setting definitions**. You should see the standard definitions, each marked active.
2. If they are missing, a developer runs `uv run --no-sync python manage.py init_settings`.

## Set one value

1. Open **Micboard > Settings** and choose **Add setting**.
2. Pick the **Definition**, for example "Battery Low Level (%)".
3. Pick the scope object the definition asks for, such as the manufacturer **Shure**. A value saved for a different scope than the definition declares is rejected.
4. Enter the value as a number (`20`), `true` or `false`, text, or JSON, matching the definition's type, and save.

## Set several values at once

- `/settings/manufacturer/` edits the manufacturer-scoped definitions for one manufacturer.
- `/settings/bulk/` applies several values in one submission.
- `/settings/` shows the current values with sensitive ones redacted.

## When a change takes effect

A change made through the admin or the settings pages is applied at once, because saving invalidates the cached value. Settings are cached for `cache_settings_minutes` (5 by default) between changes.

## If a value looks wrong

- Check the scope. A manufacturer-scoped definition uses only the row for that manufacturer, and never falls back to an organization or site row.
- Check that the value matches the definition's type.
- Check that the definition is active.
- If no value is stored, the default from `MICBOARD_CONFIG`, the package or the definition applies. See [Settings management](settings-management.md).
