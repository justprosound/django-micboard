# ADR-007: Introduce DRF API Layer with Versioning

**Status:** Proposed
**Date:** 2026-05-20
**Deciders:** (to be assigned)

## Context

django-micboard has no REST API. All user interaction goes through Django admin views (Django templates + HTMX). This means:

- No programmatic access for external integrations (third-party tools, mobile apps, automation).
- No documented API contract — all data access is admin-only.
- No serialization layer — form classes in `micboard/forms/settings.py` (297 lines) serve as the closest equivalent, but are tightly coupled to template rendering.
- Any future integration (e.g., a React frontend, mobile companion app, or external monitoring system) would require reverse-engineering the admin views.

The lack of versioning means API-breaking changes cannot be communicated or migrated gracefully.

## Decision

1. **Introduce Django REST Framework (DRF)** as the API framework (already indirectly depended-on via Django admin).
2. **Create `micboard/api/v1/`** with submodules mirroring domain structure:
   ```
   micboard/api/
     __init__.py
     v1/
       __init__.py
       urls.py
       serializers/
         hardware.py
         discovery.py
         monitoring.py
         settings.py
       views/
         chassis.py  (ViewSets)
         units.py
         channels.py
         discovery.py
         monitoring.py
         settings.py
       permissions.py
       filters.py
       pagination.py
   ```
3. **API v1 is read-only initially** — expose GET endpoints for hardware inventory, discovery status, monitoring state, and settings. This avoids needing write-side validation and conflict resolution upfront.
4. **Future versions** (v2, etc.) get new `micboard/api/v2/` namespaces without breaking v1 consumers.
5. **Admin views remain the primary UI.** The API is for programmatic consumption only.
6. **Serializer classes replace the need for form classes** — migrate settings forms to DRF serializers over time.

## Consequences

- **Positive:** External integrations become possible. API contract is documented via DRF's browsable API and schema generation. Domain-aligned serializers become the canonical data mapping layer, replacing ad-hoc form logic. Versioning ensures backward compatibility.
- **Negative:** Adds a new surface to maintain. DRF serializers add another abstraction layer alongside existing forms. Read-only v1 limits utility until write endpoints are added.
- **Migration:** (a) Add DRF to dependencies (check if already present), (b) implement v1 serializers for core models, (c) wire v1 URLs, (d) add GET endpoints for hardware and discovery domains. Do not deprecate admin views.

## Compliance

- New API versions must be backward-compatible within the same major version.
- Breaking changes require a new version namespace (v2, v3, ...).
