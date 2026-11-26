---
title: "Setting definitions reference"
description: "Every standard setting definition created by init_settings, with scope, type and default."
type: reference
audience: both
---
`manage.py init_settings` creates these standard definitions. Each one has exactly one scope (global, organization, site or manufacturer), and a stored value applies only at that scope. The default shown is the definition default, used when no value is stored and no `MICBOARD_CONFIG` or package default applies. See [Settings management](settings-management.md) for how values resolve.

| Key | Label | Scope | Type | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `battery_good_level` | Battery Good Level (%) | manufacturer | integer | `90` | Battery level above which device is considered in good condition |
| `battery_low_level` | Battery Low Level (%) | manufacturer | integer | `20` | Battery level at which to alert for low battery |
| `battery_critical_level` | Battery Critical Level (%) | manufacturer | integer | `0` | Battery level at which device is considered unreliable |
| `health_check_interval` | Health Check Interval (seconds) | manufacturer | integer | `300` | How often to check manufacturer API health |
| `api_timeout` | API Timeout (seconds) | manufacturer | integer | `30` | Request timeout for manufacturer API calls |
| `device_max_requests_per_call` | Max Devices Per API Call | manufacturer | integer | `100` | Maximum number of devices to request in a single API call |
| `supports_discovery_ips` | Supports Discovery IPs | manufacturer | boolean | `false` | Whether this manufacturer API supports IP-based device discovery |
| `supports_health_check` | Supports Health Check API | manufacturer | boolean | `false` | Whether this manufacturer provides health check endpoints |
| `discovery_enabled` | Discovery Enabled | organization | boolean | `true` | Enable automatic device discovery for this manufacturer |
| `discovery_interval_minutes` | Discovery Interval (minutes) | organization | integer | `60` | How often to run device discovery |
| `polling_enabled` | Polling Enabled | organization | boolean | `true` | Enable automatic device polling/monitoring |
| `polling_interval_seconds` | Polling Interval (seconds) | organization | integer | `300` | How often to poll devices for status updates |
| `polling_batch_size` | Polling Batch Size | organization | integer | `50` | Number of devices to poll in each batch |
| `cache_device_specs_minutes` | Cache Device Specs (minutes) | global | integer | `1440` | How long to cache device specifications |
| `cache_settings_minutes` | Cache Settings (minutes) | global | integer | `5` | How long to cache setting values |
| `log_api_calls` | Log API Calls | organization | boolean | `false` | Log details of all manufacturer API calls |
| `alert_on_device_offline_minutes` | Alert on Device Offline (minutes) | organization | integer | `30` | Send alert if device doesn't respond for this long |

Value types are entered as numbers (`300`), booleans (`true` or `false`), text, or JSON.
