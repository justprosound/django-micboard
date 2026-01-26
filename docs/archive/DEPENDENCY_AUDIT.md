# Dependency Audit - django-micboard

**Date:** January 22, 2026
**Version:** 25.10.17

## Summary

Restructured dependencies to keep core package minimal while allowing optional features via extras.

## Core Dependencies (Required)

| Package | Version | Purpose | Usage |
|---------|---------|---------|-------|
| `Django` | >=5.1,<6.0 | Web framework | Core application framework |
| `requests` | >=2.31.0 | HTTP client | Manufacturer API communication (Shure, Sennheiser) |
| `djangorestframework` | >=3.14.0 | REST API | API views and serializers |
| `asgiref` | >=3.7.0 | ASGI support | Async view support |

**Total Core:** 4 packages (~30MB installed)

## Optional Dependencies

### `realtime` - WebSocket Support

**Install:** `pip install django-micboard[realtime]`

| Package | Purpose | Usage |
|---------|---------|-------|
| `channels` | Django Channels framework | WebSocket consumer infrastructure |
| `daphne` | ASGI server | Production WebSocket server |
| `websockets` | WebSocket client | Shure API WebSocket subscriptions |

**Use Case:** Live device updates without polling
**Alternative:** Polling via cron/systemd timer

### `redis` - Redis Backend

**Install:** `pip install django-micboard[redis]`

| Package | Purpose | Usage |
|---------|---------|-------|
| `channels-redis` | Channels layer backend | Multi-process WebSocket message routing |
| `redis` | Redis client | Cache backend, session storage |

**Use Case:** Distributed deployment, caching
**Alternative:** In-memory channel layer, database cache

### `tasks` - Background Tasks

**Install:** `pip install django-micboard[tasks]`

| Package | Purpose | Usage |
|---------|---------|-------|
| `django-q2` | Task queue | Async polling, scheduled tasks |

**Use Case:** Background polling, scheduled maintenance
**Alternative:** `manage.py poll_devices` via cron/systemd

### `images` - Image Field Support

**Install:** `pip install django-micboard[images]`

| Package | Purpose | Usage |
|---------|---------|-------|
| `Pillow` | Image processing | Channel.image field (optional feature) |

**Use Case:** Custom channel images in UI
**Alternative:** Text-only labels

### `full` - All Features

**Install:** `pip install django-micboard[full]`

Installs all optional dependencies for complete feature set.

## Development Dependencies

**Install:** `pip install django-micboard[dev]`

| Package | Purpose |
|---------|---------|
| `pytest-django` | Testing framework |
| `pytest-asyncio` | Async test support |
| `pytest-cov` | Code coverage |
| `ruff` | Linting and formatting |
| `mypy` | Type checking |
| `freezegun` | Time mocking for tests |
| `pre-commit` | Git hooks |
| `build` | Package building |
| `twine` | PyPI uploads |
| `bandit` | Security linting |

## Documentation Dependencies

**Install:** `pip install django-micboard[docs]`

MkDocs and plugins for generating documentation.

## Removed Dependencies

### `urllib3`

**Reason:** Transitive dependency of `requests`, no need to pin explicitly
**Impact:** None (still installed via requests)

### `django-q2[sentry]`

**Change:** Removed `[sentry]` extra, moved to `tasks` optional group
**Reason:** Sentry integration is optional and should be user-configured
**Migration:** Add `sentry-sdk` separately if needed

## Installation Scenarios

### Minimal Installation (Core only)

```bash
pip install django-micboard
```

**Features:**
- ✅ REST API
- ✅ Polling-based updates
- ✅ Shure/Sennheiser integration
- ❌ WebSocket real-time updates
- ❌ Redis caching
- ❌ Background tasks
- ❌ Image uploads

**Best for:** Small deployments, single server, cron-based polling

### Standard Installation (Realtime)

```bash
pip install django-micboard[realtime,tasks]
```

**Features:**
- ✅ REST API
- ✅ WebSocket real-time updates
- ✅ Background task queue
- ✅ Shure/Sennheiser integration
- ❌ Redis (uses in-memory channel layer)
- ❌ Image uploads

**Best for:** Single server with real-time dashboard

### Production Installation (Full)

```bash
pip install django-micboard[full]
```

**Features:**
- ✅ All features enabled
- ✅ Redis-backed channels
- ✅ Distributed deployment support
- ✅ Background tasks
- ✅ Image uploads

**Best for:** Multi-server production deployments

## Size Comparison

| Installation | Packages | Disk Size (approx) |
|--------------|----------|---------------------|
| Core | 4 core | ~30 MB |
| + realtime | +3 packages | ~45 MB |
| + redis | +2 packages | ~50 MB |
| + tasks | +1 package | ~52 MB |
| + images | +1 package | ~65 MB |
| Full | 11 total | ~65 MB |
| + dev | +19 packages | ~120 MB |
| + docs | +16 packages | ~150 MB |

## Breaking Changes

### Migration Guide

**Old installation:**
```bash
pip install django-micboard
# All dependencies installed
```

**New installation (equivalent):**
```bash
pip install django-micboard[full]
# Same as before
```

**Minimal installation:**
```bash
pip install django-micboard
# Only core dependencies
```

### Code Changes Required

None! Optional dependencies are gracefully handled:

```python
# Existing code works with or without optional deps
try:
    from channels.layers import get_channel_layer
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False

# Fallback to polling if channels not available
if CHANNELS_AVAILABLE:
    broadcast_websocket_update()
else:
    logger.debug("Channels not available, skipping broadcast")
```

## Testing

All 72 tests pass with minimal installation:

```bash
pip install django-micboard
pip install django-micboard[dev]  # Test dependencies
pytest micboard/tests/
# 72 passed
```

## Recommendations

### For New Projects

- Start with **core only** (`pip install django-micboard`)
- Add features as needed via extras
- Use `[full]` for rapid prototyping

### For Production

- Use `[realtime,redis,tasks]` for distributed deployments
- Add `[images]` only if using custom channel images
- Monitor dependency CVEs via `safety check`

### For Development

- Always include `[dev]` extra
- Use `pre-commit` hooks for code quality
- Run `ruff check` before committing

## Future Considerations

### Potential Removals

1. **djangorestframework**: Could be optional if only WebSocket API needed
   - Would require refactoring serializers
   - Significant breaking change
   - Not recommended

2. **asgiref**: Required by Django 5.x, cannot remove

### Potential Additions

1. **prometheus-client**: For metrics export (new optional extra)
2. **sentry-sdk**: For error tracking (new optional extra)
3. **python-dotenv**: For .env file support (add to core?)

### Lighter Alternatives

None identified - current dependencies are optimal for functionality provided.

---

**Last Updated:** January 22, 2026
**Next Review:** 26.04.01 (Quarterly)
